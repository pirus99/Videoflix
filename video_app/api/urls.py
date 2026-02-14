from django.urls import path

from video_app.api.views import (
    VideoListView, VideoM3U8View, VideoSegmentView, PreviewM3U8View, PreviewSegmentView, ThumbnailView
)

urlpatterns = [
    # Video endpoints
    path('video/', VideoListView.as_view()),
    path('video/<int:video_id>/<str:resolution>/index.m3u8', VideoM3U8View.as_view()),
    # Include bitrate in the segment path so HLS player can request correct segments
    path('video/<int:video_id>/<str:resolution>/<str:segment_name>', VideoSegmentView.as_view()),
    path('preview/<int:video_id>/index.m3u8', PreviewM3U8View.as_view()),
    path('preview/<int:video_id>/<str:segment_name>', PreviewSegmentView.as_view()),
    path('thumbnail/video_<int:video_id>/thumbnail.jpg', ThumbnailView.as_view())
]
