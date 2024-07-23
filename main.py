from flask import Flask, request, Response
from dotenv import load_dotenv
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import requests
import hmac
import hashlib

# load environment variables from the .env file
load_dotenv()

spotify_client_id = os.getenv('SPOTIFY_CLIENT_ID')
spotify_client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
spotify_redirect_uri = os.getenv('SPOTIFY_REDIRECT_URI')
lastfm_api_key = os.getenv('LASTFM_API_KEY')
lastfm_shared_secret = os.getenv('LASTFM_SHARED_SECRET')

# authenticate with spotify
spotify_auth_manager = SpotifyClientCredentials(
    client_id=spotify_client_id,
    client_secret=spotify_client_secret
)
spotify = spotipy.Spotify(auth_manager=spotify_auth_manager)
app = Flask(__name__)

def lastfm_request(method, params):
    base_url = 'http://ws.audioscrobbler.com/2.0/'
    params['api_key'] = lastfm_api_key
    params['method'] = method
    params['format'] = 'json'
    response = requests.get(base_url, params=params)
    if response.status_code != 200:
        print(f"last.fm request failed with status code: {response.status_code}, reason: {response.reason}")
        return None
    try:
        return response.json()
    except ValueError:
        print("failed to decode last.fm response as json")
        return None

@app.route('/')
def home():
    return "welcome to algo-rhythm!"

@app.route('/recommend', methods=['POST'])
def recommend():
    if request.method == 'POST':
        data = request.get_json()
        print(data)  # debugging line to print incoming json data
        
        verify = data.get('verify', 'yes')
        if verify.lower() != 'yes':
            return Response("error: verification failed.", status=400)

        is_musician = data.get('is_musician')
        if is_musician == 'yes':
            musician_action = data.get('musician_action')
            if musician_action == 'update':
                artist_name = data.get('artist_name')
                update_type = data.get('update_type')
                if update_type in ['artist', 'album', 'song']:
                    query = data.get('query')
                    if update_type == 'artist':
                        recs = recommend_artists(artist_name, exclude_artist=artist_name, query=query)
                    elif update_type == 'album':
                        recs = recommend_albums(query, artist_name, exclude_artist=artist_name)
                    elif update_type == 'song':
                        recs = recommend_songs(query, artist_name, exclude_artist=artist_name)
                    return Response("\n".join(recs), content_type='text/plain')
            elif musician_action == 'find':
                input_type = data.get('input_type')
                query = data.get('query')
                artist = data.get('artist', '')
                if input_type == 'artist':
                    recs = recommend_artists(query, exclude_artist=artist)
                elif input_type == 'album':
                    recs = recommend_albums(query, artist, exclude_artist=artist)
                elif input_type == 'song':
                    recs = recommend_songs(query, artist, exclude_artist=artist)
                return Response("\n".join(recs), content_type='text/plain')
        else:
            input_type = data.get('input_type')
            query = data.get('query')
            artist = data.get('artist', '')
            if input_type == 'artist':
                recs = recommend_artists(query, exclude_artist=artist)
            elif input_type == 'album':
                recs = recommend_albums(query, artist, exclude_artist=artist)
            elif input_type == 'song':
                recs = recommend_songs(query, artist, exclude_artist=artist)
            return Response("\n".join(recs), content_type='text/plain')

    return "welcome to algo-rhythm!"

def recommend_artists(artist_name, exclude_artist=None, query=None):
    print(f"searching for similar artists to: {artist_name}")
    response = lastfm_request('artist.getsimilar', {'artist': artist_name})
    
    # initialize recommendation list
    rec_artists = []
    
    # include the specified query artist first, if provided
    if query:
        query_results = spotify.search(q=f'artist:{query}', type='artist')
        if query_results['artists']['items']:
            query_artist = query_results['artists']['items'][0]
            rec_artists.append((query_artist['name'], query_artist['external_urls']['spotify']))
    
    if response and 'similarartists' in response:
        similar_artists = response['similarartists']['artist']
        for artist in similar_artists:
            if len(rec_artists) < 3:
                if artist['name'].lower() != artist_name.lower() and (exclude_artist is None or artist['name'].lower() != exclude_artist.lower()):
                    if 'mbid' in artist:
                        spotify_link = f"https://open.spotify.com/artist/{artist['mbid']}"
                    else:
                        spotify_results = spotify.search(q=f'artist:{artist["name"]}', type='artist')
                        if spotify_results['artists']['items']:
                            spotify_link = spotify_results['artists']['items'][0]['external_urls']['spotify']
                        else:
                            continue
                    if artist['name'] != query:
                        rec_artists.append((artist['name'], spotify_link))
    
    rec_artists = ensure_smaller_artist(rec_artists)
    formatted_recs = [f"{name}\nlink: {link}" for name, link in [item[:2] for item in rec_artists]]
    print(f"found recommendations: {formatted_recs}")
    return formatted_recs

def recommend_albums(album_name, artist_name, exclude_artist=None):
    print(f"searching for albums similar to: {album_name} by {artist_name}")
    
    # verify with user that the input is correct
    user_verification = input(f"is the album '{album_name}' by '{artist_name}' correct? (yes/no): ").strip().lower()
    if user_verification != 'yes':
        return ["input verification failed. please check the album and artist names."]
    
    # search for the album on spotify
    results = spotify.search(q=f'album:{album_name} artist:{artist_name}', type='album')
    print(f"spotify search results: {results}")  # debugging line to print the search results
    
    if not results['albums']['items']:
        print(f"no albums found for: {album_name} by {artist_name}")
        return ["no similar albums found"]
    
    album = results['albums']['items'][0]
    print(f"found album: {album}")  # debugging line to print the found album
    
    # use last.fm to find similar artists
    response = lastfm_request('artist.getsimilar', {'artist': artist_name})
    print(f"last.fm artist.getsimilar response: {response}")  # debugging line to print the last.fm response
    
    if response and 'similarartists' in response and 'artist' in response['similarartists']:
        similar_artists = response['similarartists']['artist']
        
        rec_albums = []
        for similar_artist in similar_artists:
            if len(rec_albums) < 10:  # fetch more albums to filter better
                if similar_artist['name'].lower() != artist_name.lower() and (exclude_artist is None or similar_artist['name'].lower() != exclude_artist.lower()):
                    # use last.fm to find albums by the similar artist
                    artist_albums_response = lastfm_request('artist.gettopalbums', {'artist': similar_artist['name']})
                    print(f"last.fm artist.gettopalbums response for artist '{similar_artist['name']}': {artist_albums_response}")  # debugging line to print the artist albums response
                    if artist_albums_response and 'topalbums' in artist_albums_response and 'album' in artist_albums_response['topalbums']:
                        top_albums = artist_albums_response['topalbums']['album']
                        for top_album in top_albums:
                            # search spotify for the album to get the spotify link
                            spotify_results = spotify.search(q=f'album:{top_album["name"]} artist:{similar_artist["name"]}', type='album')
                            if spotify_results['albums']['items']:
                                spotify_link = spotify_results['albums']['items'][0]['external_urls']['spotify']
                                rec_albums.append((top_album['name'], similar_artist['name'], spotify_link))
                                print(f"added recommendation: {top_album['name']} by {similar_artist['name']}")  # debugging line to print added recommendations
                                break  # only take the first album from each similar artist
        
        print(f"filtered recommendations before ensuring smaller albums: {rec_albums}")  # debugging line to print the filtered recommendations
        
        # ensure the first recommendation is from a small artist
        rec_albums = ensure_smaller_album(rec_albums)
        formatted_recs = [f"{name} by {artist}\nlink: {link}" for name, artist, link in [item[:3] for item in rec_albums[:3]]]
        print(f"found recommendations: {formatted_recs}")
        return formatted_recs if formatted_recs else ["no similar albums found"]
    
    print("no similar albums found or response was invalid")
    return ["no similar albums found"]

def recommend_songs(song_name, artist_name, exclude_artist=None):
    print(f"searching for songs similar to: {song_name} by {artist_name}")
    
    # verify with user that the input is correct
    user_verification = input(f"is the song '{song_name}' by '{artist_name}' correct? (yes/no): ").strip().lower()
    if user_verification != 'yes':
        return ["input verification failed. please check the song and artist names."]
    
    # search for the song on spotify
    results = spotify.search(q=f'track:{song_name} artist:{artist_name}', type='track')
    print(f"spotify search results: {results}")  # debugging line to print the search results
    
    if not results['tracks']['items']:
        print(f"no tracks found for: {song_name} by {artist_name}")
        return ["no similar songs found"]
    
    track = results['tracks']['items'][0]
    print(f"found track: {track}")  # debugging line to print the found track
    
    # use spotify recommendations to find similar tracks
    artist_id = track['artists'][0]['id']
    recommendations = spotify.recommendations(seed_artists=[artist_id], seed_tracks=[track['id']], limit=10)
    print(f"spotify recommendations: {recommendations}")  # debugging line to print spotify recommendations
    
    rec_tracks = []
    for rec in recommendations['tracks']:
        if len(rec_tracks) < 3 and rec['artists'][0]['name'].lower() != artist_name.lower() and (exclude_artist is None or rec['artists'][0]['name'].lower() != exclude_artist.lower()):
            rec_tracks.append((rec['name'], rec['artists'][0]['name'], rec['external_urls']['spotify']))
            print(f"added recommendation: {rec['name']} by {rec['artists'][0]['name']}")  # debugging line to print added recommendations
    
    print(f"filtered recommendations before ensuring smaller songs: {rec_tracks}")  # debugging line to print the filtered recommendations
    
    # ensure the first recommendation is from a small artist
    rec_tracks = ensure_smaller_song(rec_tracks)
    formatted_recs = [f"{name} by {artist}\nlink: {link}" for name, artist, link in [item[:3] for item in rec_tracks]]
    print(f"found recommendations: {formatted_recs}")
    return formatted_recs if formatted_recs else ["no similar songs found"]

def ensure_smaller_artist(rec_artists):
    if len(rec_artists) == 0:
        return rec_artists
    
    # the last.fm request to get the artist's info
    for i, (name, link) in enumerate(rec_artists):
        response = lastfm_request('artist.getinfo', {'artist': name})
        if response and 'artist' in response and 'stats' in response['artist']:
            stats = response['artist']['stats']
            if 'listeners' in stats:
                rec_artists[i] = (name, link, int(stats['listeners']))
    
    # sort the list of recommendations by the number of listeners (ascending order)
    rec_artists.sort(key=lambda x: x[2] if len(x) > 2 else float('inf'))
    
    # return only the first artist with the smallest number of listeners
    return rec_artists[:3]

def ensure_smaller_album(rec_albums):
    if len(rec_albums) == 0:
        return rec_albums
    
    # the last.fm request to get the album's info
    for i, (album, artist, link) in enumerate(rec_albums):
        response = lastfm_request('album.getinfo', {'album': album, 'artist': artist})
        if response and 'album' in response and 'listeners' in response['album']:
            rec_albums[i] = (album, artist, link, int(response['album']['listeners']))
    
    # sort the list of recommendations by the number of listeners (ascending order)
    rec_albums.sort(key=lambda x: x[3] if len(x) > 3 else float('inf'))
    
    # return only the first album with the smallest number of listeners
    return rec_albums[:3]

def ensure_smaller_song(rec_songs):
    if len(rec_songs) == 0:
        return rec_songs
    
    # the last.fm request to get the song's info
    for i, (song, artist, link) in enumerate(rec_songs):
        response = lastfm_request('track.getinfo', {'track': song, 'artist': artist})
        if response and 'track' in response and 'listeners' in response['track']:
            rec_songs[i] = (song, artist, link, int(response['track']['listeners']))
    
    # sort the list of recommendations by the number of listeners (ascending order)
    rec_songs.sort(key=lambda x: x[3] if len(x) > 3 else float('inf'))
    
    # return only the first song with the smallest number of listeners
    return rec_songs[:3]

if __name__ == '__main__':
    app.run(debug=True)

