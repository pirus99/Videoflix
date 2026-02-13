import requests, os, time
from django.conf import settings
from django.core.cache import cache
from .transcode import generate_m3u8_file, generate_transcode_path

def get_m3u8_file(m3u8_path, video_id, recreate_file=False):
    """Helper function to read the M3U8 file content, with caching."""
    cache_key = f"m3u8_{video_id}"
    
    try: 
        cached_m3u8 = cache.get(cache_key)
        if cached_m3u8 and not recreate_file:
            return cached_m3u8
        if os.path.exists(m3u8_path) and not recreate_file:
            with open(m3u8_path, 'r') as f:
                m3u8_content = f.read()
                cache.set(cache_key, m3u8_content, timeout=60*60)  # Cache for 1 hour
                return m3u8_content
        else:
            created_m3u8 = generate_m3u8_file(m3u8_path, video_id)
            cache.set(cache_key, created_m3u8, timeout=60*60)  # Cache for 1 hour
            return created_m3u8
    except Exception as e:
        print(f"Error reading or creating M3U8 file: {e}")
        return None
        
def fetch_and_fill_imdb_metadata(video):
    """Gets a video object and fills in metadata fields from IMDb using the provided IMDb ID. Returns the updated video and the fetched data."""
    # Support two kinds of fetch_imdb_data results:
    # - a requests.Response-like object (from an HTTP/OMDb implementation)
    # - a dict (as returned by the imdbpy-based implementation in this project)
    response = fetch_imdb_data(video.imdb_id)

    # Normalize into a data dict
    if isinstance(response, dict):
        data = response
    else:
        # Try to handle a requests.Response-like object
        try:
            if hasattr(response, 'status_code') and response.status_code == 200:
                data = response.json()
            else:
                raise ValueError(f"HTTP error fetching IMDb data: {getattr(response, 'status_code', 'unknown')}")
        except Exception:
            raise

    # imdbpy returns keys like 'title','plot','poster','year','type','genre','category'
    # OMDb returns keys like 'Title','Plot','Poster','Year','Type','Genre'
    title = data.get('title') or data.get('Title')
    plot = data.get('plot') or data.get('Plot')
    poster = data.get('poster') or data.get('Poster')
    year = data.get('year') or data.get('Year')
    vtype = data.get('type') or data.get('Type')
    # genre may be a comma-separated string (OMDb) or a joined string from imdbpy
    genre = data.get('genre') or data.get('Genre') or data.get('category') or data.get('Category')

    if title:
        video.title = title
    if plot:
        video.description = plot
    if poster:
        video.poster_url = poster
        # Keep thumbnail_url in sync unless already set
        if not video.thumbnail_url:
            video.thumbnail_url = poster
    if year:
        try:
            video.release_year = int(year)
        except Exception:
            video.release_year = year
    if vtype:
        video.type = vtype
    if genre:
        # If OMDb style comma-separated string, keep it; if list-like already processed, store first as category
        if isinstance(genre, str) and ',' in genre:
            video.category = genre
        else:
            video.category = genre

    return video, data

def fetch_imdb_data(imdb_id):
    """Fetch metadata for an IMDb id using IMDbPY"""
    try:
        import imdb
        ia = imdb.IMDb()
        mid = imdb_id.replace('tt', '')
        movie = ia.get_movie(mid)
        title = movie.get('title')
        plot = None
        if movie.get('plot'):
            plot = movie.get('plot')[0]
        poster = movie.get('cover url') or movie.get('full-size cover url') or None
        year = movie.get('year')
        genres = movie.get('genres', [])
        genre = ', '.join(genres) if genres else None
        category = genres[0] if genres else None
        if poster is None:
            # Try fetching poster from OMDb as a fallback
            omdb_poster = fetch_omdb_poster(imdb_id)
            poster = omdb_poster if omdb_poster else None
        return {
            'title': title,
            'plot': plot,
            'poster': poster,
            'year': year,
            'type': movie.get('kind'),
            'genre': genre,
            'category': category,
            'director': ', '.join([d.get('name', str(d)) for d in movie.get('directors', [])]) if movie.get('directors') else None,
            'actors': ', '.join([a.get('name', str(a)) for a in movie.get('cast', [])[:5]]) if movie.get('cast') else None,
        }
    
    except Exception:
        raise RuntimeError('ImdbPY error: Failed to fetch data for IMDb ID ' + imdb_id)
    

    

def _output_dir_fs(video_id, resolution):
	return os.path.join(settings.BASE_DIR, generate_transcode_path(video_id, resolution))


def _segment_path(video_id, resolution, segment_name):
	return os.path.join(_output_dir_fs(video_id, resolution), segment_name)


def wait_for_segment_completion(video_id, resolution, segment_name, timeout=30, stable_time=2):
	"""Wait until the segment file exists and its size is stable for `stable_time` seconds.

	Returns True if file is ready, False on timeout.
	"""
	path = _segment_path(video_id, resolution, segment_name)
	start = time.time()
	last_size = -1
	stable_since = None

	while time.time() - start < timeout:
		if os.path.exists(path):
			try:
				size = os.path.getsize(path)
			except Exception:
				size = -1

			if size > 0:
				if size == last_size:
					if stable_since is None:
						stable_since = time.time()
					elif time.time() - stable_since >= stable_time:
						return True
				else:
					stable_since = None
					last_size = size
			else:
				stable_since = None
				last_size = size

		time.sleep(0.5)

	return False

def fetch_omdb_poster(imdb_id):
    url = f"http://www.omdbapi.com/?i={imdb_id}&plot=short&r=json"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            poster = data.get("Poster")
            if poster and poster != "N/A":
                return poster
    except Exception:
        pass
    return None