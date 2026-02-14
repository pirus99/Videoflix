import os, time

from django.core.cache import cache

from rest_framework import status
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from video_app.models import Video
from video_app.api.scripts import get_m3u8_file, generate_transcode_path
from video_app.api.workers import start_transcode_worker
from .serializers import TranscodeRequestSerializer

class VideoListView(APIView):
    """API view to list all videos."""

    def get(self, request):
        videos = Video.objects.all().values('id', 'title', 'description', 'thumbnail_url', 'category', 'type', 'duration', 'created_at', 'imdb_id', 'release_year')
        return Response(list(videos), status=status.HTTP_200_OK)
    
class VideoM3U8View(APIView):
    """API view to serve the M3U8 playlist for a video."""

    def get(self, request, video_id, resolution):
        from video_app.api.transcode import set_heartbeat
        
        output_path = f"media/index/video_{video_id}/"
        m3u8_path = os.path.join(output_path, 'index.m3u8')
        recreate = request.query_params.get('recreate', 'false').lower() == 'true'
        
        # Set initial heartbeat when playlist is requested
        set_heartbeat(video_id, resolution, 0)

        worker_id = str(video_id) + "_" + "_" + resolution + "_" + request.user.username

        m3u8 = get_m3u8_file(m3u8_path, video_id, recreate_file=recreate)
        start_transcode_worker(video_id, resolution, segment_name="segment_000.mp4", codec='h264', worker_id=worker_id, continuous=True)

        if m3u8 is None or m3u8.startswith("Error"):
            return Response({"error": m3u8}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        if m3u8.startswith("Failed"):
            return Response({"error": m3u8}, status=status.HTTP_202_ACCEPTED)
        return HttpResponse(m3u8, content_type='application/vnd.apple.mpegurl')
    
class VideoSegmentView(APIView):
    """API view to serve individual video segments."""

    def get(self, request, video_id, resolution, segment_name):
        from video_app.api.transcode import set_heartbeat
        from video_app.api.workers import kill_continuous_worker
        serializer = TranscodeRequestSerializer(data={'codec': 'h264', 'resolution': resolution, 'bitrate': None})
        serializer.is_valid(raise_exception=True)
        
        segment_path = generate_transcode_path(video_id, resolution)
        
        if segment_name == 'init.mp4':
            if os.path.exists(segment_path + segment_name):
                with open(segment_path + segment_name, 'rb') as f:
                    response = HttpResponse(f.read(), content_type='video/mpegts')
                    response['Content-Disposition'] = f'inline; filename="{segment_name}"'
                    return response
            else:
                worker_id = str(video_id) + "_" + "_" + resolution + "_" + request.user.username + "_init"
                start_transcode_worker(video_id, resolution, segment_name, codec='h264', worker_id=worker_id, continuous=False)
                while not os.path.exists(segment_path + segment_name):
                    print(f"Waiting for {segment_name} to be transcoded...")
                    time.sleep(1)
                with open(segment_path + segment_name, 'rb') as f:
                    response = HttpResponse(f.read(), content_type='video/mpegts')
                    response['Content-Disposition'] = f'inline; filename="{segment_name}"'
                    return response
        
        requested_segment_num = None
        try:
            if segment_name.startswith('segment_') and segment_name.endswith('.mp4'):
                requested_segment_num = int(segment_name.split('_')[1].split('.')[0])
                set_heartbeat(video_id, resolution, requested_segment_num)
        except Exception:
            pass  # Continue even if heartbeat fails
        
        # If segment exists, serve it
        if os.path.exists(segment_path + segment_name):
                with open(segment_path + segment_name, 'rb') as f:
                    response = HttpResponse(f.read(), content_type='video/mpegts')
                    response['Content-Disposition'] = f'inline; filename="{segment_name}"'
                    return response
        
        if not os.path.exists(segment_path + segment_name) and requested_segment_num is not None:
            last_transcoded_segment = -1
            for i in range(1000):  # Check up to 1000 segments
                test_seg = os.path.join(segment_path, f"segment_{i:03d}.mp4")
                if os.path.exists(test_seg):
                    last_transcoded_segment = i
                elif last_transcoded_segment >= 0:
                    break
            
            # If requested segment is beyond last transcoded, kill continuous worker
            if requested_segment_num > last_transcoded_segment + 1:
                kill_continuous_worker(video_id, resolution)
            
            worker_id = str(video_id) + "_" + "_" + resolution + "_" + request.user.username
            
            # Use single-segment transcode (not continuous) for this request
            start_transcode_worker(video_id, resolution, segment_name, codec='h264', worker_id=worker_id, continuous=False)
            while not os.path.exists(segment_path + segment_name):
                print(f"Waiting for segment {segment_name} to be transcoded...")
                time.sleep(2)
            with open(segment_path + segment_name, 'rb') as f:
                response = HttpResponse(f.read(), content_type='video/mpegts')
                response['Content-Disposition'] = f'inline; filename="{segment_name}"'
                return response
        return Response({"error": "Segment not found after transcoding."}, status=status.HTTP_404_NOT_FOUND)
    
class PreviewM3U8View(APIView):
    """API view to serve the M3U8 playlist for a preview."""

    def get(self, request, video_id):
        
        output_path = f"media/hls_preview/preview_{video_id}/"
        m3u8_path = os.path.join(output_path, 'index.m3u8')
        if not os.path.exists(m3u8_path):
            return Response({"error": "Preview M3U8 playlist not found."}, status=status.HTTP_404_NOT_FOUND)
        with open(m3u8_path, 'r') as f:
            m3u8_content = f.read()
        m3u8 = m3u8_content if m3u8_content else None
        if m3u8 is None or m3u8.startswith("Error"):
            return Response({"error": m3u8}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return HttpResponse(m3u8, content_type='application/vnd.apple.mpegurl')
    
class PreviewSegmentView(APIView):
    """API view to serve individual preview segments."""

    def get(self, request, video_id, segment_name):
        segment_path = os.path.join(f"media/hls_preview/preview_{video_id}/", segment_name)
        if os.path.exists(segment_path):
            with open(segment_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='video/mpegts')
                response['Content-Disposition'] = f'inline; filename="{segment_name}"'
                return response
        return Response({"error": "Preview segment not found."}, status=status.HTTP_404_NOT_FOUND)
    
class ThumbnailView(APIView):
    """API view to serve video thumbnails."""

    permission_classes = []  # Allow public access to thumbnails
    authentication_classes = []  # Disable authentication for thumbnail access

    def get(self, request, video_id):
        video = Video.objects.filter(id=video_id).first()
        if video and video.thumbnail_url:
            thumbnail_path = os.path.join(f'media/index/video_{video_id}/thumbnail.jpg')
            if os.path.exists(thumbnail_path):
                with open(thumbnail_path, 'rb') as f:
                    response = HttpResponse(f.read(), content_type='image/jpeg')
                    response['Content-Disposition'] = f'inline; filename="{os.path.basename(video.thumbnail_url)}"'
                    return response
        return Response({"error": "Thumbnail not found."}, status=status.HTTP_404_NOT_FOUND)
        