from ftlangdetect import detect


LANGUAGE_CODES = {

    "Kannada": "kn",

    "Hindi": "hi",

    "Tamil": "ta",

    "Telugu": "te",

    "Malayalam": "ml",

    "English": "en"

}



def detect_language(text):

    if not text:
        return None


    try:

        result = detect(
            text=text,
            low_memory=True
        )


        return result["lang"]


    except Exception:

        return None




def language_match(
        text,
        requested_language
):

    detected = detect_language(
        text
    )


    expected = LANGUAGE_CODES.get(
        requested_language
    )


    if detected == expected:

        return 30


    return 0