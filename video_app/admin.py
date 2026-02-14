from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.conf import settings
import django_rq
import os
import shutil

from .models import Video, Preview
from video_app.api.transcode import transcode_preview
from video_app.api.workers import video_post_upload_worker

def cleanup_video_media(video):
	"""Remove all media files associated with a video (original file, HLS transcodes, preview)."""
	base_dir = getattr(settings, 'BASE_DIR', os.getcwd())
	
	if video.video_file:
		try:
			if video.video_file.storage.exists(video.video_file.name):
				video.video_file.delete(save=False)
		except Exception:
			pass

	hls_dir = os.path.join(base_dir, 'media', 'hls', f'video_{video.id}')
	if os.path.exists(hls_dir):
		shutil.rmtree(hls_dir, ignore_errors=True)
	
	try:
		preview = video.preview
		cleanup_preview_media(preview)
	except Preview.DoesNotExist:
		pass


def cleanup_preview_media(preview):
	"""Remove all media files associated with a preview (HLS transcodes)."""
	base_dir = getattr(settings, 'BASE_DIR', os.getcwd())
	
	preview_hls_dir = os.path.join(base_dir, 'media', 'hls_preview', f'preview_{preview.id}')
	index_dir = os.path.join(base_dir, "media", "index", f"video_{preview.video.id}")
	if os.path.exists(preview_hls_dir):
		shutil.rmtree(preview_hls_dir, ignore_errors=True)
	if os.path.exists(index_dir):
		shutil.rmtree(index_dir, ignore_errors=True)

@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
	list_display = ('id', 'title', 'category', 'codec', 'resolution', 'duration', 'is_transcoded', 'has_preview', 'created_at')
	readonly_fields = ('codec', 'resolution', 'duration', 'is_transcoded')
	fieldsets = (
		('Video File & IMDb', {
			'fields': ('video_file', 'imdb_id'),
			'description': 'Upload a video file and optionally provide an IMDb ID to auto-fill metadata. '
			               'If no IMDb ID is given or the lookup fails, you must fill in the metadata manually below.'
		}),
		('Metadata (auto-filled from IMDb if available)', {
			'fields': ('title', 'description', 'category', 'type', 'release_year'),
			'classes': ('collapse',) if False else (), 
		}),
		('Media URLs (auto-filled from IMDb if available)', {
			'fields': ('thumbnail_url', 'poster_url'),
		}),
		('Technical Info (auto-detected from file)', {
			'fields': ('codec', 'resolution', 'duration', 'is_transcoded'),
			'classes': ('collapse',),
		}),
	)

	class Media:
		css = {
			'all': ('video_app/admin/css/video_upload.css',)
		}
		js = ('video_app/admin/js/video_upload.js',)

	def has_preview(self, obj):
		"""Check if video has a preview."""
		try:
			return obj.preview is not None and obj.preview.is_transcoded
		except Preview.DoesNotExist:
			return False
	has_preview.boolean = True
	has_preview.short_description = 'Preview'

	def save_model(self, request, obj, form, change):
		"""Save the video and enqueue background processing to prevent timeout."""
		super().save_model(request, obj, form, change)

		try:
			q = django_rq.get_queue('default')
			q.enqueue(video_post_upload_worker, obj.id)
			if obj.imdb_id:
				self.message_user(
					request,
					_('✓ Video saved. Background job started to fetch IMDb metadata and process video.'),
					level=messages.SUCCESS
				)
			else:
				# Warn about missing fields if no IMDb ID
				missing_fields = []
				if not obj.title:
					missing_fields.append('title')
				if not obj.description:
					missing_fields.append('description')
				if not obj.category:
					missing_fields.append('category')
				if not obj.type:
					missing_fields.append('type')
				
				if missing_fields:
					self.message_user(
						request,
						_('⚠ Video saved. No IMDb ID provided - please edit and fill in: %(fields)s. '
						  'Background processing started for technical metadata.') % {
							'fields': ', '.join(missing_fields)
						},
						level=messages.WARNING
					)
				else:
					self.message_user(
						request,
						_('✓ Video saved. Background job started to process video.'),
						level=messages.SUCCESS
					)
		except Exception as e:
			self.message_user(
				request,
				_('⚠ Video saved but failed to start background processing: %(error)s') % {'error': str(e)},
				level=messages.ERROR
			)

	def delete_model(self, request, obj):
		"""Delete video and all associated media files from disk."""
		cleanup_video_media(obj)
		super().delete_model(request, obj)

	def delete_queryset(self, request, queryset):
		"""Delete multiple videos and all associated media files from disk."""
		for video in queryset:
			cleanup_video_media(video)
		super().delete_queryset(request, queryset)


@admin.register(Preview)
class PreviewAdmin(admin.ModelAdmin):
	"""Admin for Preview model - 2 minute looped preview footage."""
	list_display = ('id', 'video', 'preview_duration', 'start_offset', 'status', 'is_transcoded', 'created_at')
	list_filter = ('status', 'is_transcoded')
	readonly_fields = ('status', 'is_transcoded', 'error_message', 'created_at', 'updated_at')
	fields = (
		'video', 'preview_duration', 'start_offset', 
		'status', 'is_transcoded', 'error_message', 'created_at', 'updated_at'
	)
	raw_id_fields = ('video',)
	actions = ['retranscode_previews']

	def save_model(self, request, obj, form, change):
		"""Reset transcoded status when settings change and trigger re-transcode."""
		if change:
			if 'preview_duration' in form.changed_data or 'start_offset' in form.changed_data:
				obj.is_transcoded = False
				obj.status = Preview.PreviewStatus.PENDING
				obj.error_message = None
		super().save_model(request, obj, form, change)
		
		if not change or obj.status == Preview.PreviewStatus.PENDING:
			try:
				q = django_rq.get_queue('default')
				q.enqueue(transcode_preview, obj.id)
				self.message_user(request, _('Preview transcode job started.'), level=messages.INFO)
			except Exception as e:
				self.message_user(request, _('Failed to start transcode: %s') % str(e), level=messages.WARNING)

	@admin.action(description='Re-transcode selected previews')
	def retranscode_previews(self, request, queryset):
		"""Admin action to re-transcode selected previews."""
		count = 0
		for preview in queryset:
			preview.status = Preview.PreviewStatus.PENDING
			preview.is_transcoded = False
			preview.error_message = None
			preview.save()
			try:
				q = django_rq.get_queue('default')
				q.enqueue(transcode_preview, preview.id)
				count += 1
			except Exception:
				pass
		self.message_user(request, _('%d preview transcode jobs started.') % count, level=messages.INFO)

	def delete_model(self, request, obj):
		"""Delete preview and all associated media files from disk."""
		cleanup_preview_media(obj)
		super().delete_model(request, obj)

	def delete_queryset(self, request, queryset):
		"""Delete multiple previews and all associated media files from disk."""
		for preview in queryset:
			cleanup_preview_media(preview)
		super().delete_queryset(request, queryset)