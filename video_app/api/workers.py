import os, subprocess, json, psutil
from django.conf import settings
from datetime import timedelta
import django_rq
from django_rq import enqueue

from video_app.api.transcode import transcode_video_segment, transcode_continuously, generate_transcode_path, generate_m3u8_file, get_thumbnail_from_video
from video_app.api.scripts import wait_for_segment_completion
from video_app.models import Thumbnail

def kill_continuous_worker(video_id, resolution):
	"""Kill the continuous transcode worker for a given video/resolution."""
	output_dir_fs = os.path.join(settings.BASE_DIR, generate_transcode_path(video_id, resolution))
	continuous_lock = os.path.join(output_dir_fs, 'continuous.lock')
	if not os.path.exists(continuous_lock):
		return False

	try:
		with open(continuous_lock, 'r') as lf:
			data = json.load(lf)
			pid = data.get('pid')
			worker_id = data.get('worker_id')

			# Kill the process only if it exists
			if pid:
				try:
					if psutil.pid_exists(int(pid)):
						subprocess.run(['taskkill', '/F', '/PID', str(int(pid))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
				except Exception:
					pass

			# Remove the RQ job if it exists
			if worker_id:
				try:
					queue = django_rq.get_queue('low')
					jobs = queue.get_jobs()
					for job in jobs:
						if job.id == worker_id:
							try:
								job.cancel()
							except Exception:
								pass
							break
				except Exception:
					pass

		# Remove lockfile
		try:
			os.remove(continuous_lock)
		except Exception:
			pass

		return True
	except Exception as e:
		print(f"Error killing continuous worker: {e}")
		return False


def start_transcode_worker(video_id, resolution, segment_name, codec='h264', worker_id=None, continuous=False):
	"""Helper function to start a background worker for transcoding a video segment."""
	from video_app.models import Video

	queue = django_rq.get_queue('low')
	jobs = queue.get_jobs()
	# Normalize job ids: use per-user-per-output ids for continuous workers so a user can
	# run multiple continuous workers for different videos/resolutions.
	continuous_job_id = None
	if worker_id:
		continuous_job_id = f"{worker_id}_video{video_id}_{resolution}"

	for job in jobs:
		# avoid duplicate segment jobs for same worker
		if worker_id and job.id == f"{worker_id}_{segment_name}":
			return

	# If a continuous job for this exact output already exists (same job id), wait for the
	# requested segment to be completed by the running worker instead of enqueuing another.
	if continuous and continuous_job_id:
		for job in jobs:
			if job.id == continuous_job_id:
				# Wait for requested segment to be fully written before returning to the view
				wait_for_segment_completion(video_id, resolution, segment_name, timeout=60, stable_time=2)
				return  # Continuous worker already exists for this video/resolution/user

	try:
		video = Video.objects.get(pk=video_id)
	except Video.DoesNotExist:
		return  # Cannot start worker if video does not exist

	# Determine resolution parameters
	if resolution == '480p':
		scale_param = 'scale=-2:480'
		bitrate = '1200k'
	elif resolution == '720p':
		scale_param = 'scale=-2:720'
		bitrate = '2500k'
	elif resolution == '1080p':
		scale_param = 'scale=-2:1080'
		bitrate = '5000k'
	elif resolution == '2160p':
		scale_param = 'scale=-2:2160'
		bitrate = '12000k'
	else:
		raise ValueError(f"Unsupported resolution: {resolution}")

	if video.resolution:
		try:
			orig_width, orig_height = map(int, video.resolution.split('x'))
		except Exception:
			orig_width = orig_height = None
		target_height = int(scale_param.split(':')[1])
		if orig_height and orig_height < target_height:
			scale_param = 'scale=-2:' + str(orig_height)
			if orig_width and orig_height and getattr(video, 'bitrate_kbps', None):
				bitrate = str(int(video.bitrate_kbps * 0.8)) + 'k'  # Reduce bitrate for lower resolution

		codec_param = 'libx264' 

	if getattr(video, 'audio_codec', None) == 'aac':
		audio_param = 'copy'
	else:
		audio_param = 'aac'
		
	index_path = os.path.join(settings.BASE_DIR, f"media/index/video_{video_id}/index.m3u8")
	segment_duration = None
	try:
		with open(index_path, 'r', encoding='utf-8') as f:
			lines = [ln.strip() for ln in f.readlines()]

		target_basename = os.path.basename(segment_name)
		for i, line in enumerate(lines):
			if line == target_basename or line.endswith('/' + target_basename) or line.endswith('\\' + target_basename):
				# search backwards for the nearest #EXTINF: line
				for j in range(i - 1, -1, -1):
					if lines[j].startswith('#EXTINF:'):
						val = lines[j].split(':', 1)[1].split(',')[0].strip()
						try:
							segment_duration = float(val)
						except Exception:
							segment_duration = None
						break
				break

	except Exception:
		segment_duration = None
		
	if not continuous:
		# If a continuous transcode is running for same video/resolution/user, kill it so this segment job can run
		if worker_id:
			# Only kill an existing continuous worker for this output if it belongs to the same user
			output_dir_fs = os.path.join(settings.BASE_DIR, generate_transcode_path(video_id, resolution))
			continuous_lock = os.path.join(output_dir_fs, 'continuous.lock')
			if os.path.exists(continuous_lock):
				try:
					with open(continuous_lock, 'r') as lf:
						data = json.load(lf)
						existing_worker = data.get('worker_id')
						# If the lockfile indicates a worker for the same user, kill it to allow this segment job
						if existing_worker and worker_id and (existing_worker == continuous_job_id or existing_worker.startswith(f"{worker_id}_") or existing_worker == worker_id):
							kill_continuous_worker(video_id, resolution)
				except Exception:
					pass
		transcode_video_segment(video_id, resolution, scale_param, segment_name, codec_param, bitrate, audio_param, segment_duration=segment_duration or 5)
		#queue.enqueue(transcode_video_segment, video_id, resolution, scale_param, segment_name, codec_param, bitrate, audio_param, segment_duration, job_id=worker_id + segment_name)
	else:
		# Enqueue a continuous job with a per-output job id and pass that id into the worker so
		# the worker writes it into the lockfile. This allows multiple continuous workers per user
		# for different videos/resolutions while preventing duplicates for the same output.
		if continuous_job_id:
			queue.enqueue(
				transcode_continuously,
				video_id,
				resolution,
				scale_param,
				segment_name,
				codec_param,
				bitrate,
				audio_param,
				segment_duration or 5,
				continuous_job_id,
				job_id=continuous_job_id,
			)
			# Wait for requested segment to be completed by ffmpeg before returning
			wait_for_segment_completion(video_id, resolution, segment_name, timeout=60, stable_time=2)
		else:
			queue.enqueue(transcode_continuously, video_id, resolution, scale_param, segment_name, codec_param, bitrate, audio_param, segment_duration=segment_duration or 5)
			wait_for_segment_completion(video_id, resolution, segment_name, timeout=60, stable_time=2)

def video_post_upload_worker(video_id):
	"""Background worker to process a newly uploaded video.

	Performs:
	1. IMDb metadata fetch (if imdb_id is set)
	2. FFprobe to extract technical metadata
	3. Create/update Preview and trigger preview transcode

	This runs in RQ to prevent request timeouts during upload.
	"""
	from video_app.models import Video, Preview
	from video_app.api.scripts import fetch_and_fill_imdb_metadata
	from video_app.api.transcode import probe_a_video, transcode_preview

	try:
		video = Video.objects.get(pk=video_id)
	except Video.DoesNotExist:
		return {'error': f'Video {video_id} not found'}

	result = {
		'video_id': video_id,
		'imdb_fetched': False,
		'imdb_error': None,
		'probe_success': False,
		'probe_error': None,
		'preview_created': False,
	}

	# 1. Fetch IMDb metadata if imdb_id is provided
	if video.imdb_id:
		try:
			video, data = fetch_and_fill_imdb_metadata(video)
			video.save()
			result['imdb_fetched'] = True
			result['imdb_title'] = data.get('title')
			result['imdb_year'] = data.get('year')
			print(f"video_post_upload_worker: IMDb metadata fetched for video {video_id}: {result.get('imdb_title')} ({result.get('imdb_year')})")
		except Exception as e:
			result['imdb_error'] = str(e)
			print(f"video_post_upload_worker: IMDb fetch failed for video {video_id}: {result['imdb_error']}")

	# 2. Probe video file for technical metadata
	try:
		path = video.video_file.path
		info = probe_a_video(path)

		changed = False
		# video codec
		vcodec = info.get('video_codec')
		if vcodec and video.codec != vcodec:
			video.codec = vcodec
			changed = True

		# audio codec
		acodec = info.get('audio_codec')
		if acodec and video.audio_codec != acodec:
			video.audio_codec = acodec
			changed = True

		# resolution -> store as 'WxH'
		w = info.get('width')
		h = info.get('height')
		if w and h:
			res = f"{w}x{h}"
			if video.resolution != res:
				video.resolution = res
				changed = True

		# duration -> DurationField expects timedelta
		ds = info.get('duration_seconds')
		if ds:
			try:
				td = timedelta(seconds=int(round(ds)))
				if video.duration != td:
					video.duration = td
					changed = True
			except Exception:
				pass

		if changed:
			video.save()

		result['probe_success'] = True
		result['probe_info'] = info
		print(f"video_post_upload_worker: probe info for video {video_id}: {result.get('probe_info')}")

	except Exception as e:
		result['probe_error'] = str(e)
		print(f"video_post_upload_worker: probe failed for video {video_id}: {result['probe_error']}")
		return result
	
	# 3. Get thumbnail from video if not already set
	if video.thumbnail_url == '' or video.thumbnail_url is None:
			print(f"video_post_upload_worker: Generating thumbnail for video {video_id}...")
			thumbnail_object = Thumbnail.objects.create(video=video)
			thumbnail_object.image = get_thumbnail_from_video(video.id)
			thumbnail_object.save()
			site_url = os.getenv('SITE_URL', default='http://localhost:8000')
			app_url = site_url + 'api/thumbnail/video_' + str(video.id)
			video.poster_url = app_url + '/' + 'thumbnail.jpg'
			video.thumbnail_url = video.poster_url
			video.save()

	# 4. Create Preview and trigger transcode
	duration_seconds = info.get('duration_seconds') or 0

	# Calculate smart start offset (start at 10% of video, or 0 if short)
	if duration_seconds > 180:  # If video is longer than 3 minutes
		start_offset = int(duration_seconds * 0.1)  # Start at 10%
	else:
		start_offset = 0

	# Preview duration: 2 minutes or video length if shorter
	preview_duration = min(120, int(duration_seconds)) if duration_seconds > 0 else 120

	try:
		# Get or create Preview
		preview, created = Preview.objects.get_or_create(
			video=video,
			defaults={
				'preview_duration': preview_duration,
				'start_offset': start_offset,
				'status': Preview.PreviewStatus.PENDING,
			}
		)

		if not created:
			# Video file was replaced, reset preview
			preview.preview_duration = preview_duration
			preview.start_offset = start_offset
			preview.status = Preview.PreviewStatus.PENDING
			preview.is_transcoded = False
			preview.error_message = None
			preview.save()

		# Enqueue the preview transcode job
		q = django_rq.get_queue('low')
		q.enqueue(transcode_preview, preview.id)
		result['preview_created'] = created
		result['preview_id'] = preview.id

		# Enqueue M3U8 generation for the full video
		m3u8_output_path = f"media/index/video_{video_id}/"
		m3u8_path = os.path.join(m3u8_output_path, 'index.m3u8')
		q.enqueue(generate_m3u8_file, m3u8_path, video_id)
		
	except Exception as e:
		result['preview_error'] = str(e)

	return result
