from django.db import models

# Create your models here.

class Video(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=255, blank=True, default='', help_text='Leave blank to auto-fill from IMDb')
    description = models.TextField(blank=True, default='', help_text='Leave blank to auto-fill from IMDb')
    thumbnail_url = models.URLField(blank=True, null=True, help_text='Leave blank to auto-fill from IMDb')
    video_file = models.FileField(upload_to='media/videos/')
    category = models.CharField(max_length=100, blank=True, default='', help_text='Leave blank to auto-fill from IMDb genre')
    type = models.CharField(max_length=50, blank=True, default='', help_text='movie, series, etc. - auto-filled from IMDb')
    codec = models.CharField(max_length=50, blank=True, default='')
    resolution = models.CharField(max_length=20, blank=True, default='')
    audio_codec = models.CharField(max_length=50, blank=True, default='')
    poster_url = models.URLField(blank=True, null=True)
    imdb_id = models.CharField(max_length=32, blank=True, null=True)
    release_year = models.IntegerField(blank=True, null=True)
    duration = models.DurationField(blank=True, null=True)
    # Flag to indicate if the video has been transcoded (prevents re-transcoding)
    is_transcoded = models.BooleanField(default=False)

    def __str__(self):
        return self.title


class Preview(models.Model):
    """Preview model for 2-minute looped HLS preview footage."""
    
    class PreviewStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
    
    video = models.OneToOneField(Video, on_delete=models.CASCADE, related_name='preview')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Preview duration - default 2 minutes (120 seconds)
    preview_duration = models.IntegerField(default=120, help_text='Preview duration in seconds')
    # Start time offset for the preview (where to start in the video)
    start_offset = models.IntegerField(default=0, help_text='Start offset in seconds')
    # Processing status
    status = models.CharField(
        max_length=20,
        choices=PreviewStatus.choices,
        default=PreviewStatus.PENDING
    )
    # Error message if processing failed
    error_message = models.TextField(blank=True, null=True)
    # Flag to indicate if preview has been transcoded
    is_transcoded = models.BooleanField(default=False)

    def __str__(self):
        return f"Preview for {self.video.title}"

    class Meta:
        verbose_name = 'Preview'
        verbose_name_plural = 'Previews'
