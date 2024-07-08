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
    if input_type == 'album' or input_type == 'song':
        query = input(f"Enter {input_type} name: ").strip()
        artist = input("Enter the artist name: ").strip()
        confirm = input(f"You entered '{query}' by '{artist}'. Is this correct? (yes/no): ").strip().lower()
        if confirm == 'yes':
            return input_type, query, artist
        else:
            print("Let's try again.")
            return get_user_input()
    else:
        query = input(f"Enter the {input_type} name: ").strip()
        return input_type, query, None

def recommend(input_type, query, artist=None):
    if input_type == 'artist':
        return recommend_artists(query)
    elif input_type == 'album':
        return recommend_albums(query, artist)
    elif input_type == 'song':
        return recommend_songs(query, artist)

def recommend_artists(artist_name):
    results = spotify.search(q=f'artist:{artist_name}', type='artist')
    if results['artists']['items']:
        artist = results['artists']['items'][0]
        recommendations = spotify.artist_related_artists(artist['id'])
        rec_artists = [(rec['name'], rec['external_urls']['spotify']) for rec in recommendations['artists'][:3]]
        rec_artists = ensure_smaller_artist(rec_artists)
        formatted_recs = [f"{name} (Link: {link})" for name, link in rec_artists]
        return formatted_recs
    return []

def recommend_albums(album_name, artist_name):
    results = spotify.search(q=f'album:{album_name} artist:{artist_name}', type='album')
    if results['albums']['items']:
        album = results['albums']['items'][0]
        artist_id = album['artists'][0]['id']
        recommendations = spotify.artist_albums(artist_id, album_type='album', limit=3)
        rec_albums = [f"{rec['name']} by {rec['artists'][0]['name']} (Link: {rec['external_urls']['spotify']})" for rec in recommendations['items']]
        return rec_albums
    return []

def recommend_songs(song_name, artist_name):
    results = spotify.search(q=f'track:{song_name} artist:{artist_name}', type='track')
    if results['tracks']['items']:
        track = results['tracks']['items'][0]
        recommendations = spotify.recommendations(seed_tracks=[track['id']], limit=3)
        rec_songs = [f"{rec['name']} by {rec['artists'][0]['name']} (Album: {rec['album']['name']})\nLink: {rec['external_urls']['spotify']}" for rec in recommendations['tracks']]
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
    for rec in recommendations:
        song_details, _ = rec.rsplit('\nLink: ', 1)
        feedback = input(f"Do you like '{song_details}'? (yes/no/never heard of): ").strip().lower()
        if feedback == 'yes':
            print(f"Great! Adding '{song_details}' to your liked list.")
        elif feedback == 'no':
            print(f"Okay, removing '{song_details}' from recommendations.")
        elif feedback == 'never heard of':
            print(f"Maybe give '{song_details}' a listen to see if you like them.")
        else:
            print(f"Invalid input, skipping '{song_details}'.")

def user_feedback(recommendations):
    print("\nHere are your recommendations:")
    for rec in recommendations:
        print(f"- {rec}")
    get_user_feedback(recommendations)

def artist_mode_recommendations(artist_name):
    recommendations = {}
    
    # related artists
    recommendations['artists'] = recommend_artists(artist_name)
    
    # albums similar to the latest release
    albums = spotify.search(q=f'artist:{artist_name}', type='album', limit=1)
    if albums['albums']['items']:
        latest_album_id = albums['albums']['items'][0]['id']
        recommendations['albums'] = recommend_albums(albums['albums']['items'][0]['name'], artist_name)
    else:
        recommendations['albums'] = []

    # songs similar to their top track
    top_tracks = spotify.artist_top_tracks(albums['albums']['items'][0]['artists'][0]['id'])
    if top_tracks['tracks']:
        top_song_id = top_tracks['tracks'][0]['id']
        recommendations['songs'] = recommend_songs(top_tracks['tracks'][0]['name'], artist_name)
    else:
        recommendations['songs'] = []

    return recommendations

def manage_algorithm(artist_name, recommendations):
    print("\nHere are your algorithm's current recommendations:")
    for category, recs in recommendations.items():
        print(f"{category.capitalize()}:")
        for rec in recs:
            print(f" - {rec}")

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
                        recommendations[category].append(new_rec)
                elif action == 'remove':
                    rem_rec = input(f"Enter the name of the {category[:-1]} to remove: ").strip()
                    recommendations[category] = [rec for rec in recommendations[category] if rec != rem_rec]
            else:
                print("Invalid category.")
        else:
            print("Invalid action.")
    return recommendations

def main():
    print("Starting the algo-rhythm...\n")
    is_musician = input("Are you a musician? (yes/no): ").strip().lower()
    if is_musician == 'yes':
        musician_action = input("Do you want to find a recommendation or manage your algorithm? (find/manage): ").strip().lower()
        if musician_action == 'find':
            input_type, query, artist = get_user_input()
            recommendations = recommend(input_type, query, artist)
            if recommendations:
                print("\nRecommendations:")
                for rec in recommendations:
                    print(f"- {rec}")
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
        input_type, query, artist = get_user_input()
        recommendations = recommend(input_type, query, artist)
        if recommendations:
            print("\nRecommendations:")
            for rec in recommendations:
                print(f"- {rec}")
        else:
            print("Sorry, no recommendations found.")

if __name__ == "__main__":
    main()
