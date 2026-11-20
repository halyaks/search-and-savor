import math


from app.language_service import language_match



# ---------------------------------------
# Recipe keywords
# ---------------------------------------

RECIPE_KEYWORDS = [

    "recipe",

    "cooking",

    "cook",

    "ingredients",

    "how to make",

    "preparation",

    "homemade",

    "food",

    "snack",

    "masala",

    "bhel",

    "churmuri"

]



# ---------------------------------------
# Language keywords
# ---------------------------------------

LANGUAGE_KEYWORDS = {

    "Kannada": [

        "kannada",

        "ಕನ್ನಡ",

        "ರೆಸಿಪಿ",

        "ಮಾಡುವ ವಿಧಾನ",

        "ಬೇಲ್",

        "ಭೇಲ್",

        "ಚುರುಮುರಿ"

    ],


    "Hindi": [

        "hindi",

        "हिंदी",

        "रेसिपी",

        "बनाने",

        "विधि"

    ],


    "Tamil": [

        "tamil",

        "தமிழ்"

    ],


    "Telugu": [

        "telugu",

        "తెలుగు"

    ],


    "Malayalam": [

        "malayalam",

        "മലയാളം"

    ]

}




# ---------------------------------------
# Words indicating wrong language
# ---------------------------------------

WRONG_LANGUAGE_KEYWORDS = {


    "Kannada": [

        "hindi",

        "हिंदी",

        "tamil",

        "தமிழ்",

        "telugu",

        "తెలుగు"

    ],


    "Hindi": [

        "kannada",

        "ಕನ್ನಡ",

        "tamil",

        "தமிழ்"

    ],


    "Tamil": [

        "kannada",

        "ಕನ್ನಡ",

        "hindi",

        "हिंदी"

    ]

}




# ---------------------------------------
# Recipe scoring
# ---------------------------------------

def recipe_score(text):

    score = 0


    for keyword in RECIPE_KEYWORDS:

        if keyword.lower() in text.lower():

            score += 10



    return min(
        score,
        50
    )




# ---------------------------------------
# Metadata language scoring
# ---------------------------------------

def metadata_language_score(
        text,
        language
):

    score = 0


    keywords = LANGUAGE_KEYWORDS.get(
        language,
        []
    )


    for keyword in keywords:

        if keyword.lower() in text.lower():

            score += 20



    return min(
        score,
        100
    )




# ---------------------------------------
# Wrong language penalty
# ---------------------------------------

def wrong_language_penalty(
        text,
        language
):

    penalty = 0


    wrong_words = WRONG_LANGUAGE_KEYWORDS.get(
        language,
        []
    )


    for word in wrong_words:

        if word.lower() in text.lower():

            penalty += 50



    return penalty




# ---------------------------------------
# View scoring
# ---------------------------------------

def view_score(views):

    return math.log10(
        views + 1
    )




# ---------------------------------------
# Final Search & Savor ranking
# ---------------------------------------

def calculate_score(
        video,
        transcript,
        language
):


    combined_text = (

        video["title"].lower()

        + " "

        + video["description"].lower()

        + " "

        + transcript.lower()

    )



    recipe = recipe_score(
        combined_text
    )



    transcript_language_score = language_match(

        transcript,

        language

    )



    metadata_score = metadata_language_score(

        combined_text,

        language

    )



    language_total = max(

        transcript_language_score,

        metadata_score

    )



    views = view_score(

        video["views"]

    )



    penalty = wrong_language_penalty(

        combined_text,

        language

    )



    # --------------------------------
    # Search & Savor Algorithm
    #
    # Recipe       45%
    # Language     40%
    # Popularity   15%
    # --------------------------------

    final_score = (

        recipe * 0.45

        +

        language_total * 0.40

        +

        views * 0.15

        -

        penalty

    )



    video["recipe_score"] = recipe


    video["language_score"] = language_total


    video["search_score"] = round(

        final_score,

        2

    )


    return video