import requests

from app.config import YOUTUBE_API_KEY

from app.transcript_service import get_transcript

from app.ranking_service import calculate_score
from app.language_service import detect_language



SEARCH_URL = (
    "https://www.googleapis.com/youtube/v3/search"
)


VIDEOS_URL = (
    "https://www.googleapis.com/youtube/v3/videos"
)

LANGUAGE_TERMS = {
    "Kannada": "Kannada",
    "Hindi": "Hindi",
    "Tamil": "Tamil",
    "Telugu": "Telugu",
    "Malayalam": "Malayalam",
    "English": "English"
}


def search_videos(
        dish,
        language
):

    language_score = 0
    language_term = LANGUAGE_TERMS.get(
    language,
    language
    )

    query = (
    f"{dish} recipe cooking tutorial {language_term}"
    )



    # ------------------------
    # Search YouTube
    # ------------------------

    params = {

        "part":
            "snippet",

        "q":
            query,

        "type":
            "video",

        "videoDuration": "medium",

        "maxResults":
            50,

        "key":
            YOUTUBE_API_KEY
    }



    response = requests.get(

        SEARCH_URL,

        params=params,

        timeout=30

    )


    response.raise_for_status()


    data=response.json()



    ids=[]


    for item in data.get(
        "items",
        []
    ):

        ids.append(
            item["id"]["videoId"]
        )



    if not ids:

        return []




    # ------------------------
    # Get details
    # ------------------------


    params={

        "part":
            "snippet,statistics",

        "id":
            ",".join(ids),

        "key":
            YOUTUBE_API_KEY

    }



    response=requests.get(

        VIDEOS_URL,

        params=params,

        timeout=30

    )


    data=response.json()



    videos=[]



    for item in data.get(
        "items",
        []
    ):


        videos.append({

            "id":
                item["id"],


            "title":
                item["snippet"]["title"],


            "description":
                item["snippet"].get(
                    "description",
                    ""
                ),


            "channel":
                item["snippet"]["channelTitle"],


            "thumbnail":
                item["snippet"]
                ["thumbnails"]
                ["high"]
                ["url"],


            "views":
                int(
                    item.get(
                        "statistics",
                        {}
                    )
                    .get(
                        "viewCount",
                        0
                    )
                ),


            "video_url":
                (
                    "https://youtube.com/watch?v="
                    + item["id"]
                )

        })



  
    

    
    # ------------------------
    # Initial popularity sort
    # ------------------------


    videos.sort(

        key=lambda x:x["views"],

        reverse=True

    )


    # only top 15 transcript checks

    ranked=[]



    for video in videos[:15]:


        transcript = get_transcript(
            video["id"]
        )


        # -----------------------------
        # Metadata language scoring
        # -----------------------------

        


        title = video["title"].lower()

        channel = video["channel"].lower()


        if language.lower() in title:

            language_score += 20


        if language.lower() in channel:

            language_score += 20


        video["metadata_language_score"] = language_score



        print("================================")
        print("TITLE:", video["title"])
        print("TRANSCRIPT LENGTH:", len(transcript))
        print("DETECTED:", detect_language(transcript))
        print("METADATA LANGUAGE SCORE:", language_score)
        print("================================")



        ranked.append(

            calculate_score(

                video,

                transcript,

                language

            )

        )



    ranked.sort(

        key=lambda x:

        x["search_score"],

        reverse=True

    )


    return ranked[:5]