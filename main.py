from dotenv import load_dotenv
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import requests
import hmac
import hashlib

# load environment variables from the .env file
load_dotenv()

SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
SPOTIPY_REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI')
LASTFM_API_KEY = os.getenv('LASTFM_API_KEY')
LASTFM_SHARED_SECRET = os.getenv('LASTFM_SHARED_SECRET')

# authenticate with spotify
spotify_auth_manager = SpotifyClientCredentials(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET
)
spotify = spotipy.Spotify(auth_manager=spotify_auth_manager)

def lastfm_request(endpoint, params):
    base_url = 'http://ws.audioscrobbler.com/2.0/'
    params['api_key'] = LASTFM_API_KEY  # add your api key to the parameters
    params['format'] = 'json'
    response = requests.get(base_url + endpoint, params=params)
    return response.json()

def create_signature(params, secret):
    # sort parameters alphabetically and concatenate them into a single string
    sorted_params = ''.join(f"{key}{params[key]}" for key in sorted(params))
     
    # create the signature using hmac and the shared secret
    signature = hmac.new(secret.encode(), sorted_params.encode(), hashlib.md5).hexdigest()
    return signature

def get_user_input():
    input_type = input("Enter type (artist, album, song): ").strip().lower()
    if input_type == 'artist':
        query = input(f"Enter the {input_type} name: ").strip()
    elif input_type in ['album', 'song']:
        query = input(f"Enter {input_type} name: ").strip()
        artist = input(f"Enter the artist name for the {input_type}: ").strip()
        verify = input(f"You entered '{query}' by '{artist}', is this correct? (yes/no): ").strip().lower()
        if verify != 'yes':
            print("Let's try again.")
            return get_user_input()
        query = f"{query} by {artist}"
    else:
        print("Invalid type.")
        return get_user_input()
    return input_type, query

def recommend(input_type, query):
    if input_type == 'artist':
        return recommend_artists(query)
    elif input_type == 'album':
        return recommend_albums(query)
    elif input_type == 'song':
        return recommend_songs(query)

def recommend_artists(artist_name):
    results = spotify.search(q=f'artist:{artist_name}', type='artist')
    if results['artists']['items']:
        artist = results['artists']['items'][0]
        recommendations = spotify.artist_related_artists(artist['id'])
        rec_artists = [(rec['name'], rec['external_urls']['spotify']) for rec in recommendations['artists'][:3]]
        rec_artists = ensure_smaller_artist(rec_artists)
        return rec_artists
    return []

def recommend_albums(album_name):
    album, artist = album_name.split(" by ")
    results = spotify.search(q=f'album:{album} artist:{artist}', type='album')
    if results['albums']['items']:
        album = results['albums']['items'][0]
        artist_id = album['artists'][0]['id']
        recommendations = spotify.artist_albums(artist_id, album_type='album', limit=3)
        rec_albums = [(rec['name'], rec['external_urls']['spotify']) for rec in recommendations['items']]
        return rec_albums
    return []

def recommend_songs(song_name):
    song, artist = song_name.split(" by ")
    results = spotify.search(q=f'track:{song} artist:{artist}', type='track')
    if results['tracks']['items']:
        track = results['tracks']['items'][0]
        recommendations = spotify.recommendations(seed_tracks=[track['id']], limit=3)
        rec_songs = [(rec['name'], rec['external_urls']['spotify']) for rec in recommendations['tracks']]
        return rec_songs
    return []

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
    if smaller_artists:
        return smaller_artists[0]
    else:
        return recommendations[0]

def ensure_smaller_artist(recommendations):
    smaller_artist = filter_smaller_artists(recommendations)
    recommendations[0] = smaller_artist
    return recommendations

def get_user_feedback(recommendations):
    for rec, link in recommendations:
        feedback = input(f"Do you like '{rec}'? (yes/no/never heard of): ").strip().lower()
        if feedback == 'yes':
            print(f"Great! Adding '{rec}' to your liked list.")
        elif feedback == 'no':
            print(f"Okay, removing '{rec}' from recommendations.")
        elif feedback == 'never heard of':
            print(f"Maybe give '{rec}' a listen to see if you like them.")
        else:
            print(f"Invalid input, skipping '{rec}'.")

def user_feedback(recommendations):
    print("\nHere are your recommendations:")
    for rec, link in recommendations:
        print(f"- {rec} (Link: {link})")
    get_user_feedback(recommendations)

def artist_mode_recommendations(artist_name):
    recommendations = {}

    # related artists
    recommendations['artists'] = recommend_artists(artist_name)
    
    # ensure maximum of 3 recommendations and at least one smaller artist
    if len(recommendations['artists']) < 3:
        # add additional recommendations from last.fm if needed
        params = {
            'method': 'artist.getsimilar',
            'artist': artist_name,
        }
        lastfm_recs = lastfm_request('', params).get('similarartists', {}).get('artist', [])
        for artist in lastfm_recs:
            if len(recommendations['artists']) >= 3:
                break
            if artist['name'] not in [a[0] for a in recommendations['artists']]:
                recommendations['artists'].append((artist['name'], f"https://www.last.fm/music/{artist['name'].replace(' ', '+')}"))
        recommendations['artists'] = ensure_smaller_artist(recommendations['artists'])

    # albums similar to the latest release
    albums = spotify.search(q=f'artist:{artist_name}', type='album', limit=1)
    if albums['albums']['items']:
        latest_album_id = albums['albums']['items'][0]['id']
        recommendations['albums'] = recommend_albums(albums['albums']['items'][0]['name'])
    else:
        recommendations['albums'] = []

    # songs similar to their top track
    top_tracks = spotify.artist_top_tracks(albums['albums']['items'][0]['artists'][0]['id'])
    if top_tracks['tracks']:
        top_song_id = top_tracks['tracks'][0]['id']
        recommendations['songs'] = recommend_songs(top_tracks['tracks'][0]['name'])
    else:
        recommendations['songs'] = []

    return recommendations

def manage_algorithm(artist_name, recommendations):
    print("\nHere are your algorithm's current recommendations:")
    for category, recs in recommendations.items():
        print(f"{category.capitalize()}:")
        for rec, link in recs:
            print(f" - {rec} (Link: {link})")

    while True:
        action = input("\nDo you want to add or remove a recommendation? (add/remove/done): ").strip().lower()
        if action == 'done':
            break
        elif action in ['add', 'remove']:
            category = input("Which category do you want to modify? (artists/albums/songs): ").strip().lower()
            if category in recommendations:
                if action == 'add':
                    new_rec = input(f"Enter the name of the {category[:-1]} to add: ").strip()
                    if len(recommendations[category]) >= 3:
                        print(f"Cannot add more than 3 recommendations in the {category} category. Remove something first.")
                    else:
                        # dummy link for user-added recommendations
                        new_link = "https://www.example.com"
                        recommendations[category].append((new_rec, new_link))
                elif action == 'remove':
                    rem_rec = input(f"Enter the name of the {category[:-1]} to remove: ").strip()
                    recommendations[category] = [rec for rec in recommendations[category] if rec[0] != rem_rec]
            else:
                print("Invalid category.")
        else:
            print("Invalid action.")
    return recommendations

def main():
    is_musician = input("Are you a musician? (yes/no): ").strip().lower()
    if is_musician == 'yes':
        musician_action = input("Do you want to find a recommendation or manage your algorithm? (find/manage): ").strip().lower()
        if musician_action == 'find':
            input_type, query = get_user_input()
            recommendations = recommend(input_type, query)
            if recommendations:
                print("\nRecommendations:")
                for rec, link in recommendations:
                    print(f"- {rec} (Link: {link})")
                user_feedback(recommendations)
            else:
                print("Sorry, no recommendations found.")
        elif musician_action == 'manage':
            artist_name = input("Enter your artist name: ").strip()
            recommendations = artist_mode_recommendations(artist_name)
            recommendations = manage_algorithm(artist_name, recommendations)
            user_feedback(recommendations)
        else:
            print("Invalid option.")
    else:
        input_type, query = get_user_input()
        recommendations = recommend(input_type, query)
        if recommendations:
            print("\nRecommendations:")
            for rec, link in recommendations:
                print(f"- {rec} (Link: {link})")
            user_feedback(recommendations)
        else:
            print("Sorry, no recommendations found.")

if __name__ == '__main__':
    main()

