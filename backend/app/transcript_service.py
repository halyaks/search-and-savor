from youtube_transcript_api import YouTubeTranscriptApi



def get_transcript(video_id):

    try:

        api = YouTubeTranscriptApi()


        transcript = api.fetch(
            video_id
        )


        text = " ".join(

            item.text

            for item in transcript

        )


        return text.lower()



    except Exception:

        return ""