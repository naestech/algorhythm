from flask import Flask, request, Response
from dotenv import load_dotenv
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import requests
import hmac
import hashlib

# Load environment variables from the .env file
load_dotenv()

SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI')
LASTFM_API_KEY = os.getenv('LASTFM_API_KEY')
LASTFM_SHARED_SECRET = os.getenv('LASTFM_SHARED_SECRET')

# Authenticate with Spotify
spotify_auth_manager = SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
)
spotify = spotipy.Spotify(auth_manager=spotify_auth_manager)
app = Flask(__name__)

def lastfm_request(method, params):
    base_url = 'http://ws.audioscrobbler.com/2.0/'
    params['api_key'] = LASTFM_API_KEY
    params['method'] = method
    params['format'] = 'json'
    response = requests.get(base_url, params=params)
    if response.status_code != 200:
        print(f"Last.fm request failed with status code: {response.status_code}, reason: {response.reason}")
        return None
    try:
        return response.json()
    except ValueError:
        print("Failed to decode Last.fm response as JSON")
        return None

@app.route('/')
def home():
    return "Welcome to Algo-Rhythm!"

@app.route('/recommend', methods=['POST'])
def recommend():
    if request.method == 'POST':
        data = request.get_json()
        print(data)  # Debugging line to print incoming JSON data
        
        verify = data.get('verify', 'yes')
        if verify.lower() != 'yes':
            return Response("Error: verification failed.", status=400)

        is_musician = data.get('is_musician')
        if is_musician == 'yes':
            musician_action = data.get('musician_action')
            if musician_action == 'update':
                artist_name = data.get('artist_name')
                update_type = data.get('update_type')
                if update_type in ['artist', 'album', 'song']:
                    query = data.get('query')
                    if update_type == 'artist':
                        recs = recommend_artists(artist_name, exclude_artist=artist_name)
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

    return "Welcome to Algo-Rhythm!"

def recommend_artists(artist_name, exclude_artist=None):
    print(f"Searching for similar artists to: {artist_name}")
    response = lastfm_request('artist.getsimilar', {'artist': artist_name})
    if response and 'similarartists' in response:
        similar_artists = response['similarartists']['artist']
        rec_artists = []
        for artist in similar_artists:
            if len(rec_artists) < 3:
                if artist['name'].lower() != artist_name.lower() and (exclude_artist is None or artist['name'].lower() != exclude_artist.lower()):
                    # Check if 'mbid' exists, otherwise use artist name to search on Spotify
                    if 'mbid' in artist:
                        spotify_link = f"https://open.spotify.com/artist/{artist['mbid']}"
                    else:
                        # Search Spotify for the artist's name to get the Spotify link
                        spotify_results = spotify.search(q=f'artist:{artist["name"]}', type='artist')
                        if spotify_results['artists']['items']:
                            spotify_link = spotify_results['artists']['items'][0]['external_urls']['spotify']
                        else:
                            continue  # Skip if no Spotify link is found
                    rec_artists.append((artist['name'], spotify_link))
        rec_artists = ensure_smaller_artist(rec_artists)
        formatted_recs = [f"{name}\nlink: {link}" for name, link in rec_artists]
        print(f"Found recommendations: {formatted_recs}")
        return formatted_recs
    print("No similar artists found or response was invalid")
    return ["No similar artists found"]

def recommend_albums(album_name, artist_name, exclude_artist=None):
    print(f"Searching for albums similar to: {album_name} by {artist_name}")
    
    # Verify with user that the input is correct
    user_verification = input(f"Is the album '{album_name}' by '{artist_name}' correct? (yes/no): ").strip().lower()
    if user_verification != 'yes':
        return ["Input verification failed. Please check the album and artist names."]
    
    # Search for the album on Spotify
    results = spotify.search(q=f'album:{album_name} artist:{artist_name}', type='album')
    print(f"Spotify search results: {results}")  # Debugging line to print the search results
    
    if not results['albums']['items']:
        print(f"No albums found for: {album_name} by {artist_name}")
        return ["No similar albums found"]
    
    album = results['albums']['items'][0]
    print(f"Found album: {album}")  # Debugging line to print the found album
    
    # Use Last.fm to find similar artists
    response = lastfm_request('artist.getsimilar', {'artist': artist_name})
    print(f"Last.fm artist.getsimilar response: {response}")  # Debugging line to print the Last.fm response
    
    if response and 'similarartists' in response and 'artist' in response['similarartists']:
        similar_artists = response['similarartists']['artist']
        
        rec_albums = []
        for similar_artist in similar_artists:
            if len(rec_albums) < 10:  # Fetch more albums to filter better
                if similar_artist['name'].lower() != artist_name.lower() and (exclude_artist is None or similar_artist['name'].lower() != exclude_artist.lower()):
                    # Use Last.fm to find albums by the similar artist
                    artist_albums_response = lastfm_request('artist.gettopalbums', {'artist': similar_artist['name']})
                    print(f"Last.fm artist.gettopalbums response for artist '{similar_artist['name']}': {artist_albums_response}")  # Debugging line to print the artist albums response
                    if artist_albums_response and 'topalbums' in artist_albums_response and 'album' in artist_albums_response['topalbums']:
                        top_albums = artist_albums_response['topalbums']['album']
                        for top_album in top_albums:
                            # Search Spotify for the album to get the Spotify link
                            spotify_results = spotify.search(q=f'album:{top_album["name"]} artist:{similar_artist["name"]}', type='album')
                            if spotify_results['albums']['items']:
                                spotify_link = spotify_results['albums']['items'][0]['external_urls']['spotify']
                                rec_albums.append((top_album['name'], similar_artist['name'], spotify_link))
                                print(f"Added recommendation: {top_album['name']} by {similar_artist['name']}")  # Debugging line to print added recommendations
                                break  # Only take the first album from each similar artist
        
        print(f"Filtered recommendations before ensuring smaller albums: {rec_albums}")  # Debugging line to print the filtered recommendations
        
        # Ensure the first recommendation is from a small artist
        rec_albums = ensure_smaller_album(rec_albums)
        formatted_recs = [f"{name} by {artist}\nlink: {link}" for name, artist, link in rec_albums[:3]]  # Return only the first 3 recommendations
        print(f"Found recommendations: {formatted_recs}")
        return formatted_recs if formatted_recs else ["No similar albums found"]
    
    print("No similar albums found or response was invalid")
    return ["No similar albums found"]

def recommend_songs(song_name, artist_name, exclude_artist=None):
    print(f"Searching for songs similar to: {song_name} by {artist_name}")
    results = spotify.search(q=f'track:{song_name} artist:{artist_name}', type='track')
    if results['tracks']['items']:
        track = results['tracks']['items'][0]
        recommendations = spotify.recommendations(seed_tracks=[track['id']], limit=50)['tracks']
        rec_songs = []
        for rec in recommendations:
            if len(rec_songs) < 3:
                if (rec['name'].lower() != song_name.lower() or rec['artists'][0]['name'].lower() != artist_name.lower()) and (exclude_artist is None or rec['artists'][0]['name'].lower() != exclude_artist.lower()):
                    rec_songs.append(f"{rec['name']} by {rec['artists'][0]['name']} (album: {rec['album']['name']})\nlink: {rec['external_urls']['spotify']}")
        formatted_recs = rec_songs[:3]  # Return only the first 3 recommendations
        print(f"Found recommendations: {formatted_recs}")
        return formatted_recs if formatted_recs else ["No similar songs found"]
    print("No similar songs found or response was invalid")
    return ["No similar songs found"]

def get_artist_popularity(artist_name):
    results = spotify.search(q=f'artist:{artist_name}', type='artist')
    if results['artists']['items']:
        artist = results['artists']['items'][0]
        return artist['followers']['total']
    return 0

def filter_smaller_artists(recommendations):
    smaller_artists = []
    for artist, link in recommendations:
        if get_artist_popularity(artist) < 200000:
            smaller_artists.append((artist, link))
    return smaller_artists

def ensure_smaller_artist(recommendations):
    smaller_artists = filter_smaller_artists(recommendations)
    if smaller_artists:
        return smaller_artists[:3]  # Return only the first 3 smaller artists
    else:
        return recommendations[:3]  # Return the first 3 recommendations if no smaller artists found

def filter_smaller_albums(recommendations):
    smaller_albums = []
    for name, artist, link in recommendations:
        if get_artist_popularity(artist) < 200000:
            smaller_albums.append((name, artist, link))
    return smaller_albums

def ensure_smaller_album(recommendations):
    smaller_albums = filter_smaller_albums(recommendations)
    if smaller_albums:
        # Ensure the first recommendation is from a small artist
        return smaller_albums[:1] + [rec for rec in recommendations if rec not in smaller_albums][:2]
    else:
        return recommendations[:3]  # Return the first 3 recommendations if no smaller albums found

if __name__ == "__main__":
    app.run(debug=True)
