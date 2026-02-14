import os
import json
from django.apps import apps
import subprocess
import time
import psutil

from django.core.cache import cache

from video_app.models import Video

# Heartbeat helpers ---------------------------------------------------------
def _heartbeat_key(video_id, resolution):
	return f"heartbeat_{video_id}_{resolution}"

def set_heartbeat(video_id, resolution, segment_number):
	"""Set the last requested segment number and timestamp for a video/resolution."""
	try:
		cache.set(_heartbeat_key(video_id, resolution), {'segment': int(segment_number), 'ts': time.time()}, timeout=None)
	except Exception:
		pass

def get_heartbeat(video_id, resolution):
	try:
		return cache.get(_heartbeat_key(video_id, resolution))
	except Exception:
		return None

def clear_heartbeat(video_id, resolution):
	try:
		cache.delete(_heartbeat_key(video_id, resolution))
	except Exception:
		pass

def lock_a_file(lockfile_path):
    """Check for a lockfile to indicate that a process is running. Or create a lockfile if it doesn't exist."""
    try:
        # Ensure parent directory exists (handles cases where callers
        # compute lockfile paths but haven't created the dirs yet).
        parent = os.path.dirname(lockfile_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        if os.path.exists(lockfile_path):
            return False 
        else:
            with open(lockfile_path, 'w') as f:
                f.write(str(os.getpid()))
            return True
    except Exception:
        # On any failure, return False to indicate we couldn't acquire the lock.
        return False
		
def get_rid_of_lockfile(lockfile_path):
	"""Remove the lockfile to indicate that the process has finished."""
	if os.path.exists(lockfile_path):
		os.remove(lockfile_path)

def generate_transcode_path(video_id, resolution):
    """Generate a unique output directory path for the transcoded video based on video ID and resolution."""
    return f"media/transcode/video_{video_id}/{resolution}/"

def get_keyframes(video_path):
	"""Use ffprobe to extract keyframe timestamps from a video."""
	try:
		cmd = [
			"ffprobe",
			"-v", "error",
			"-select_streams", "v:0",
			"-skip_frame", "nokey",
			"-show_frames",
			"-show_entries", "frame=best_effort_timestamp_time",
			"-of", "json",
			video_path
		]

		# run without shell=True when passing a list
		ffprobe_output = subprocess.run(cmd, capture_output=True, text=True)
		if ffprobe_output.returncode != 0:
			print(ffprobe_output.stderr)
			print(cmd)
			return []

		data = json.loads(ffprobe_output.stdout)

		keyframes = []
		for f in data.get("frames", []):
			ts = f.get("best_effort_timestamp_time")
			if ts is not None:
				keyframes.append(float(ts))

		# Ensure 0.0 exists
		if keyframes and keyframes[0] > 0.001:
			keyframes.insert(0, 0.0)

		keyframes = sorted(set(keyframes))
		return keyframes
	except Exception as e:
		print(f"Error extracting keyframes: {e}")
		return []

def generate_m3u8_file(m3u8_path, video_id):
    """Generate the M3U8 file for Video Files with ffprobe and ffmpeg."""
    # ensure lockfile is always defined so exception handlers can refer to it safely
    lockfile = None
    try: 
        # Get the directory of the M3U8 file
        output_dir = os.path.dirname(m3u8_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Extract keyframes from the original video
        video_path = "media/" + Video.objects.get(pk=video_id).video_file.name
        
        lockfile = os.path.join(output_dir, "lockfile.lock")
        if not lock_a_file(lockfile):
            return "Failed to acquire lock for M3U8 generation. Generation is already in progress."
        
        keyframes = get_keyframes(video_path)
        print(f"Extracted {len(keyframes)} keyframes for video {video_id}")

        if not keyframes:
            get_rid_of_lockfile(lockfile)
            return "Error failed to extract keyframes. M3U8 generation cannot proceed."

        # Generate the M3U8 content
        m3u8_content = "#EXTM3U\n#EXT-X-VERSION:6\n"
        m3u8_content += "#EXT-X-MEDIA-SEQUENCE:0\n"
        m3u8_content += "#EXT-X-MAP:URI=\"init.mp4\"\n"
        m3u8_content += "#EXT-X-ALLOW-CACHE:YES\n"
        m3u8_content += "#EXT-X-PLAYLIST-TYPE:EVENT\n"
        m3u8_content += f"#EXT-X-TARGETDURATION:{int(keyframes[3]-keyframes[0])+1}\n"
        m3u8_content += "#EXT-X-START:TIME-OFFSET=0.01,PRECISE=NO\n"
        for i in range(int((len(keyframes) - 1) / 3) + 1):
            duration = (keyframes[i + 1] - keyframes[i]) * 3
            m3u8_content += "#EXT-X-DISCONTINUITY\n"
            m3u8_content += f"#EXTINF:{duration:.3f},\nsegment_{i:03d}.mp4\n"
        m3u8_content += "#EXT-X-ENDLIST\n"

        # Write the M3U8 content to the file
        with open(m3u8_path, 'w') as f:
            f.write(m3u8_content)

        get_rid_of_lockfile(lockfile)

        return m3u8_content
    
    except Exception as e:
        # only try to remove lockfile if it was created/assigned
        if lockfile:
            try:
                get_rid_of_lockfile(lockfile)
            except Exception:
                pass
        return "Error generating M3U8 file. Details: " + str(e)
	
def transcode_video_segment(video_id, resolution, scale_param, segment_name, codec_param, bitrate, audio_param, segment_duration):
	"""Transcode a single video segment using FFmpeg."""
	video = Video.objects.get(pk=video_id)
	input_path = video.video_file.path
	output_dir = generate_transcode_path(video_id, resolution)
	os.makedirs(output_dir, exist_ok=True)
	output_path = os.path.join(output_dir, segment_name)

	lockfile = output_path + "lockfile.lock"
	if not lock_a_file(lockfile):
		return "Failed to acquire lock for segment transcoding. Transcoding is already in progress."
	

	try:
		if not segment_name == 'init.mp4':
			segment_number = int(segment_name.split('_')[1].split('.')[0])
			start_time = str(float(segment_duration) * segment_number)
			cmd = [
				"ffmpeg", "-y",
				"-ss", start_time,
				"-to", str(float(start_time) + float(segment_duration) / 3 * 2),
				"-i", input_path,
				"-vf", scale_param,
				"-c:v", codec_param,
				"-preset", "medium",
				"-b:v", bitrate,
				"-c:a", audio_param,
				"-ar", "48000",
				"-movflags", "+empty_moov+default_base_moof",
				"-force_key_frames", f"expr:gte(t,n_forced*{segment_duration / 3})",
				"-reset_timestamps", "0",
				"-fflags", "+genpts",
				output_path  # segment_000.mp4
			]
		else:
			cmd = [
				"ffmpeg", "-y",
				"-i", input_path,
				"-vf", scale_param,
				"-c:v", codec_param,
				"-preset", "fast",
				"-b:v", bitrate,
				"-c:a", audio_param,
				"-ar", "48000",
				"-t", "0",  # Short duration to create the init segment
				"-f", "mp4",
				"-fflags", "+genpts",
				"-movflags", "+faststart+frag_keyframe+empty_moov+default_base_moof",
				output_path  # init.mp4
			]
			
		result = subprocess.run(
			cmd,
			stdout=subprocess.DEVNULL,
			stderr=subprocess.PIPE,
			text=True,
			timeout=300,
		)
	
		if result.returncode != 0:
			raise Exception(f"FFmpeg error: {result.stderr}")

		get_rid_of_lockfile(lockfile)
		return "Success"
	except Exception as e:
		get_rid_of_lockfile(lockfile)
		return f"Error transcoding segment: {str(e)}"
	
def transcode_continuously(video_id, resolution, scale_param, segment_name, codec_param, bitrate, audio_param, segment_duration, worker_id=None):
	"""Continuously transcode segments as they are requested until the entire video is transcoded.
	
	Uses a single long-running FFmpeg process that transcodes from the starting segment onwards.
	Heartbeat monitoring:
	- Pauses process when 40 segments ahead of last requested segment
	- Resumes process when ahead count drops below 20 segments
	- Kills process after 10 minutes of no segment requests
	"""
	video = Video.objects.get(pk=video_id)
	input_path = video.video_file.path
	output_dir = generate_transcode_path(video_id, resolution)
	os.makedirs(output_dir, exist_ok=True)
	segment_number = int(segment_name.split('_')[1].split('.')[0])
	start_time = str((float(segment_duration)) * segment_number)
	print(f"Starting continuous transcode for video {video_id} at resolution {resolution} from segment {segment_name} with start time {start_time}")

	if os.path.exists(os.path.join(output_dir, segment_name)):
		print(f"Segment {segment_name} already transcoded, skipping transcoding.")
		return "Success"

	cmd = [
		"ffmpeg", "-y",
		"-ss", start_time,
		"-i", input_path,
		"-vf", scale_param,
		"-c:v", codec_param,
		"-preset", "medium",
		"-b:v", bitrate,
		"-c:a", audio_param,
		"-ar", "48000",
		"-reset_timestamps", "0",
		"-f", "hls",
		"-hls_time", str(segment_duration),
		"-hls_playlist_type", "event",
		"-hls_segment_type", "fmp4",
		"-hls_flags", "independent_segments+omit_endlist",
		"-hls_fmp4_init_filename", "init.mp4",
		"-hls_segment_filename", os.path.join(output_dir, "segment_%03d.mp4"),
		output_dir
	]

	continuous_lock = os.path.join(output_dir, 'continuous.lock')
	proc = None
	process_suspended = False

	try:
		# Start FFmpeg process
		proc = subprocess.Popen(
			cmd,
			stdout=subprocess.DEVNULL,
			stderr=subprocess.PIPE,
			text=True,
		)

		# Write lockfile with pid and optional worker id
		try:
			with open(continuous_lock, 'w') as lf:
				json.dump({'pid': proc.pid, 'worker_id': worker_id}, lf)
		except Exception:
			pass

		# Get psutil Process object for suspend/resume capabilities
		try:
			ps_proc = psutil.Process(proc.pid)
		except:
			ps_proc = None

		# Monitor heartbeat and control process
		while proc.poll() is None:  # While process is still running
			time.sleep(2)  # Check every 2 seconds
			
			heartbeat_data = get_heartbeat(video_id, resolution)
			
			if heartbeat_data:
				last_requested_segment = heartbeat_data.get('segment', 0)
				last_request_time = heartbeat_data.get('ts', time.time())
				time_since_request = time.time() - last_request_time
				
				# Calculate how many segments have been transcoded
				transcoded_count = 0
				for i in range(segment_number, segment_number + 1000):  # Check up to 1000 segments
					seg_file = os.path.join(output_dir, f"segment_{i:03d}.mp4")
					if os.path.exists(seg_file):
						transcoded_count = i - segment_number + 1
					else:
						break
				
				current_transcoded_segment = segment_number + transcoded_count - 1
				segments_ahead = current_transcoded_segment - last_requested_segment
				
				# Kill if no requests for 10 minutes (600 seconds)
				if time_since_request > 600:
					print(f"No segment requests for 10 minutes. Killing transcode for video {video_id} resolution {resolution}.")
					try:
						if ps_proc:
							ps_proc.kill()
						else:
							proc.kill()
					except:
						pass
					clear_heartbeat(video_id, resolution)
					return "Killed due to inactivity"
				
				# Pause if 40 segments ahead
				if segments_ahead >= 40 and not process_suspended:
					print(f"Pausing transcode: {segments_ahead} segments ahead of playback (video {video_id}, {resolution})")
					try:
						if ps_proc:
							ps_proc.suspend()
							process_suspended = True
					except Exception as e:
						print(f"Failed to suspend process: {e}")
				
				# Resume if below 20 segments ahead
				elif segments_ahead < 20 and process_suspended:
					print(f"Resuming transcode: {segments_ahead} segments ahead (video {video_id}, {resolution})")
					try:
						if ps_proc:
							ps_proc.resume()
							process_suspended = False
					except Exception as e:
						print(f"Failed to resume process: {e}")

		# Process finished, check return code
		if proc.returncode != 0:
			stderr_output = ""
			try:
				_, stderr_output = proc.communicate(timeout=1)
			except:
				pass
			print(f"FFmpeg process exited with code {proc.returncode}: {stderr_output}")
			return f"FFmpeg error: exit code {proc.returncode}"
		
		return "Success"
		
	except Exception as e:
		print(f"Fatal error in continuous transcode: {str(e)}")
		# Try to kill the process if it's still running
		if proc and proc.poll() is None:
			try:
				proc.kill()
			except:
				pass
		return f"Error in continuous transcode: {str(e)}"
	finally:
		try:
			get_rid_of_lockfile(continuous_lock)
		except Exception:
			pass
		try:
			clear_heartbeat(video_id, resolution)
		except Exception:
			pass
	
def transcode_preview(preview_id):
    """RQ worker for preview transcoding (fixed 480p @ 900k)."""
    Preview = apps.get_model('video_app', 'Preview')
    preview = Preview.objects.select_related('video').get(id=preview_id)

    preview.status = Preview.PreviewStatus.PROCESSING
    preview.save(update_fields=['status'])
    # Use configured preview settings if available on the model
    preview_start_offset = preview.start_offset if getattr(preview, 'start_offset', None) is not None else 20
    preview_preview_duration = preview.preview_duration if getattr(preview, 'preview_duration', None) is not None else 120
    preview_path = os.path.join("media", "hls_preview", f"preview_{preview_id}")
    playlist = os.path.join(preview_path, "index.m3u8")
    lockfile = os.path.join(preview_path, "lockfile.lock")
    os.makedirs(preview_path, exist_ok=True)
    print(f"Initiating transcode for preview {preview_id} with start offset {preview_start_offset} and duration {preview_preview_duration}")
    if not lock_a_file(lockfile):
        preview.status = Preview.PreviewStatus.FAILED
        preview.error_message = "Failed to acquire lock for preview transcoding. Transcoding is already in progress."
        preview.save(update_fields=['status', 'error_message'])
        return "Failed to acquire lock"

    try:
        # Ensure we pass a plain filesystem path (string) to ffmpeg — FieldFile objects cause the 'expected str' error
        input_path = getattr(preview.video.video_file, 'path', None) or str(preview.video.video_file)
        input_path = str(input_path)

        # Build ffmpeg command: options first, then the output playlist path
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(preview_start_offset),
            "-i", input_path,
            "-t", str(preview_preview_duration),
            "-vf", "scale=-2:480",
            "-c:v", "libx264", "-preset", "medium", "-b:v", "900k",
            "-an",
            "-movflags", "+faststart+frag_keyframe+empty_moov+default_base_moof",
            "-f", "hls",
            "-hls_time", "5",
            "-hls_playlist_type", "vod",
            "-hls_segment_type", "fmp4",
            "-hls_fmp4_init_filename", "init.mp4",
            "-hls_segment_filename", os.path.join(preview_path, "preview_%03d.mp4"),
            playlist,
        ]

        # Run ffmpeg and capture stderr for diagnostics
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=300)
        if result.returncode != 0:
            preview.status = Preview.PreviewStatus.FAILED
            preview.error_message = (result.stderr or "ffmpeg failed").strip()[:2000]
            preview.save(update_fields=['status', 'error_message'])
            return f"Error transcoding preview: {preview.error_message}"

        preview.is_transcoded = True
        preview.status = Preview.PreviewStatus.COMPLETED
        preview.error_message = None
        preview.save(update_fields=['is_transcoded', 'status', 'error_message'])
        return "Success"

    except Exception as e:
        preview.status = Preview.PreviewStatus.FAILED
        preview.error_message = str(e)
        preview.save(update_fields=['status', 'error_message'])
        return f"Error transcoding preview: {str(e)}"
    finally:
        try:
            get_rid_of_lockfile(lockfile)
        except Exception:
            pass
	
def _run_cmd(cmd):
	try:
		completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
		return completed.stdout
	except subprocess.CalledProcessError as e:
		raise RuntimeError(f"Command failed: {e.stderr.strip()}")
	
def probe_a_video(path):
	"""Probe the video using ffprobe and return width, height and bitrate for audio and Video in kbps and duration in seconds.

	Returns dict: {'width': int, 'height': int, 'bitrate_kbps': int, 'video_codec': str, 'audio_codec': str, 'audio_bitrate_kbps': int, 'duration_seconds': float}
	"""
	if not os.path.exists(path):
		raise FileNotFoundError(path)

	cmd = [
		'ffprobe', '-v', 'error', '-show_entries', 'stream=index,codec_type,codec_name,width,height,bit_rate', '-of', 'json', path
	]
	out = _run_cmd(cmd)
	data = json.loads(out)

	video_stream = None
	audio_stream = None
	if 'streams' in data and len(data['streams']) > 0:
		for s in data['streams']:
			if s.get('codec_type') == 'video' and video_stream is None:
				video_stream = s
			if s.get('codec_type') == 'audio' and audio_stream is None:
				audio_stream = s

	width = None
	height = None
	bit_rate = None
	video_codec = None
	audio_codec = None
	audio_bit_rate = None

	if video_stream:
		width = int(video_stream.get('width')) if video_stream.get('width') else None
		height = int(video_stream.get('height')) if video_stream.get('height') else None
		# stream bit_rate might be None for some codecs
		bit_rate = video_stream.get('bit_rate')
		video_codec = video_stream.get('codec_name')

	if audio_stream:
		audio_codec = audio_stream.get('codec_name')
		audio_bit_rate = audio_stream.get('bit_rate')

	cmd2 = ['ffprobe', '-v', 'error', '-show_entries', 'format=bit_rate,duration', '-of', 'json', path]
	out2 = _run_cmd(cmd2)
	data2 = json.loads(out2)
	fmt = data2.get('format')

	if fmt:
		if not bit_rate:
			bit_rate = fmt.get('bit_rate')
		duration = fmt.get('duration')

	bitrate_kbps = None
	if bit_rate:
		try:
			bitrate_kbps = int(int(bit_rate) / 1000)
		except Exception:
			bitrate_kbps = None

	audio_bitrate_kbps = None
	if audio_bit_rate:
		try:
			audio_bitrate_kbps = int(int(audio_bit_rate) / 1000)
		except Exception:
			audio_bitrate_kbps = None

	duration_seconds = None
	try:
		if 'duration' in locals() and duration:
			duration_seconds = float(duration)
	except Exception:
		duration_seconds = None

	return {
		'width': width,
		'height': height,
		'bitrate_kbps': bitrate_kbps,
		'video_codec': video_codec,
		'audio_codec': audio_codec,
		'audio_bitrate_kbps': audio_bitrate_kbps,
		'duration_seconds': duration_seconds,
	}

def get_thumbnail_from_video(video_id):
	video = Video.objects.get(pk=video_id)
	input_path = video.video_file.path
	output_dir = os.path.join("media", "index", f"video_{video_id}")
	os.makedirs(output_dir, exist_ok=True)
	output_path = os.path.join(output_dir, "thumbnail.jpg")
	timestamp = video.duration / 10

	cmd = [
		"ffmpeg", "-y",
		"-ss", str(timestamp),
		"-i", input_path,
		"-frames:v", "1",
		output_path
	]

	try:
		result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
		if result.returncode != 0:
			raise Exception(f"FFmpeg error: {result.stderr.strip()}")
		return output_path
	except Exception as e:
		print(f"Error generating thumbnail: {str(e)}")
		return None
