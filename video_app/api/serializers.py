from rest_framework import serializers


class TranscodeRequestSerializer(serializers.Serializer):
    codec = serializers.ChoiceField(choices=['h264', 'h265'], required=False, allow_null=True)
    resolution = serializers.ChoiceField(choices=['360p', '480p', '720p', '1080p', '2160p'])
    bitrate = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    ALLOWED = {
        'h264': {
            '360p': ['500k', '800k'],
            '480p': ['1000k', '1500k'],
            '720p': ['2500k', '3500k'],
            '1080p': ['4500k', '6000k'],
            '2160p': ['12000k', '20000k'],
        },
        'h265': {
            '360p': ['350k', '500k'],
            '480p': ['700k', '1100k'],
            '720p': ['1500k', '2500k'],
            '1080p': ['3000k', '4500k'],
            '2160p': ['8000k', '12000k'],
        }
    }

    def validate_bitrate(self, value):
        s = str(value).lower().strip()
        if s.endswith('k'):
            norm = s
        elif s.isdigit():
            norm = f"{int(s)}k"
        else:
            norm = None

        codec = self.initial_data.get('codec') or 'h264'
        if codec not in self.ALLOWED:
            codec = 'h264'
            try:
                self.initial_data['codec'] = codec
            except Exception:
                pass

        res = self.initial_data.get('resolution')
        allowed = self.ALLOWED.get(codec, {}).get(res)
        if not allowed:
            raise serializers.ValidationError('Unsupported resolution for codec')

        def to_int_k(b):
            try:
                return int(str(b).lower().rstrip('k'))
            except Exception:
                return -1

        if norm is None or norm not in allowed:
            best = max(allowed, key=to_int_k)
            return best

        return norm

    def validate(self, attrs):
        codec = attrs.get('codec') or 'h264'
        if codec not in self.ALLOWED:
            codec = 'h264'
        attrs['codec'] = codec

        res = attrs.get('resolution')
        allowed = self.ALLOWED.get(codec, {}).get(res)
        if not allowed:
            raise serializers.ValidationError({'resolution': 'Unsupported resolution for codec'})

        def to_int_k(b):
            try:
                return int(str(b).lower().rstrip('k'))
            except Exception:
                return -1
            
        bitrate = attrs.get('bitrate')
        norm = None
        if bitrate:
            try:
                norm = self.validate_bitrate(bitrate)
            except serializers.ValidationError:
                norm = None

        if norm is None or norm not in allowed:
            best = max(allowed, key=to_int_k)
            attrs['bitrate'] = best
        else:
            attrs['bitrate'] = norm

        return attrs


class PreviewSerializer(serializers.Serializer):
    """Serializer for Preview model data."""
    id = serializers.IntegerField(read_only=True)
    video_id = serializers.IntegerField(read_only=True)
    video_title = serializers.CharField(source='video.title', read_only=True)
    preview_duration = serializers.IntegerField(read_only=True)
    start_offset = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    is_transcoded = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)