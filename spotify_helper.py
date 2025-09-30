import os
import re
from typing import List
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
except Exception:
    spotipy = None

SPOTIFY_RE = re.compile(r'open\.spotify\.com/(track|playlist|album)/([A-Za-z0-9]+)')
API = None

def init_spotify():
    global API
    client_id = os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
    if not client_id or not client_secret:
        return None
    if spotipy is None:
        return None
    auth = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
    API = spotipy.Spotify(auth_manager=auth)
    return API

def spotify_to_queries(url_or_query: str) -> List[str]:
    if API is None:
        init_spotify()
    m = SPOTIFY_RE.search(url_or_query)
    if not m:
        return [url_or_query]
    kind, id_ = m.group(1), m.group(2)
    queries = []
    try:
        if kind == 'track':
            t = API.track(id_)
            artists = ', '.join(a['name'] for a in t['artists'])
            queries.append(f"{artists} - {t['name']}")
        elif kind == 'playlist':
            pl = API.playlist_items(id_)
            for item in pl['items']:
                track = item.get('track')
                if not track:
                    continue
                artists = ', '.join(a['name'] for a in track['artists'])
                queries.append(f"{artists} - {track['name']}")
        elif kind == 'album':
            album = API.album_tracks(id_)
            for t in album['items']:
                artists = ', '.join(a['name'] for a in t['artists'])
                queries.append(f"{artists} - {t['name']}")
    except Exception:
        return [url_or_query]
    return queries
