from django.core.management.base import BaseCommand, CommandError

from video_app.api.transcode import cleanup_inactive_transcodes


class Command(BaseCommand):
    help = 'Cleanup inactive per-user transcode folders older than given seconds'

    def add_arguments(self, parser):
        parser.add_argument('--base-dir', type=str, default='media/transcode', help='Base transcode directory')
        parser.add_argument('--inactive-seconds', type=int, default=3600, help='Inactive threshold in seconds')

    def handle(self, *args, **options):
        base_dir = options['base_dir']
        inactive_seconds = options['inactive_seconds']
        removed = cleanup_inactive_transcodes(base_dir=base_dir, inactive_seconds=inactive_seconds)
        self.stdout.write(self.style.SUCCESS(f'Removed {len(removed)} directories'))
        for p in removed:
            self.stdout.write(p)
