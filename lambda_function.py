import json
import datetime
import time
import os
import logging
import facebook
import unidecode
import requests

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


""" --- Helpers to build responses which match the structure of the necessary dialog actions --- """


def elicit_slot(session_attributes, intent_name, slots, slot_to_elicit, message, response_card):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'ElicitSlot',
            'intentName': intent_name,
            'slots': slots,
            'slotToElicit': slot_to_elicit,
            'message': message,
            'responseCard': response_card
        }
    }


def confirm_intent(session_attributes, intent_name, slots, message, response_card):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'ConfirmIntent',
            'intentName': intent_name,
            'slots': slots,
            'message': message,
            'responseCard': response_card
        }
    }


def close(session_attributes, fulfillment_state, message):
    print(message)
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Close',
            'fulfillmentState': fulfillment_state,
            'message': (message[:635] + '..') if len(message) > 639 else message
        }
    }


def delegate(session_attributes, slots):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Delegate',
            'slots': slots
        }
    }


def build_response_card(title, subtitle, options):
    """
    Build a responseCard with a title, subtitle, and an optional set of options which should be displayed as buttons.
    """
    buttons = None
    if options is not None:
        buttons = []
        for i in range(min(5, len(options))):
            buttons.append(options[i])

    return {
        'contentType': 'application/vnd.amazonaws.card.generic',
        'version': 1,
        'genericAttachments': [{
            'title': title,
            'subTitle': subtitle,
            'buttons': buttons
        }]
    }


""" --- Helper Functions --- """


def parse_info():
    with open('info.json') as data_file:
        return json.load(data_file)


def parse_timetable():
    with open('timetable.json') as data_file:
        return json.load(data_file)


def locate_current_dj(area, next_=None, previous_=None):
    if not area:
        return False

    current_time = datetime.datetime.today()
    area = unidecode.unidecode(area.lower())

    timetable = parse_timetable()

    for part in timetable:
        for area in timetable[part].get('areas', []):
            area_selector = timetable[part]['areas'][area]
            area_name = area_selector.get('id', part)

            if area in unidecode.unidecode(area_name.lower()):
                area_length = len(area_selector.get('dj', []))
                for index, dj in enumerate(area_selector.get('dj', [])):
                    start = datetime.datetime.strptime(dj.get('start'), '%b %d %Y %I:%M%p')
                    end = datetime.datetime.strptime(dj.get('end'), '%b %d %Y %I:%M%p')
                    if start <= current_time <= end:
                        if next_:
                            if index < (area_length - 1):
                                next_ = area_selector.get('dj', [])[index + 1]
                            return next_.get('dj', '')
                        if previous_:
                            if index > 0:
                                previous_ = area_selector.get('dj', [])[index - 1]
                            return previous_.get('dj', '')
                        return dj.get('dj', '')
    return False


def locate_dj(dj):
    if not dj:
        return False

    dj = unidecode.unidecode(dj.lower())

    results = []
    timetable = parse_timetable()

    for part in timetable:
        party_name = timetable[part].get('id', part)

        for area in timetable[part].get('areas', []):
            area_selector = timetable[part]['areas'][area]
            area_name = area_selector.get('id', part)

            for found_dj in area_selector.get('dj', []):
                if dj in unidecode.unidecode(found_dj.get('dj', '').lower()):
                    results.append({
                        'party': party_name,
                        'area': area_name,
                        'dj': found_dj.get('dj', ''),
                        'start': found_dj.get('start'),
                        'end': found_dj.get('end')
                    })

    return results


def locate_lineup_area(area, party):
    if not area:
        return False
    if not party:
        return False

    area = unidecode.unidecode(area.lower())
    party = unidecode.unidecode(party.lower())

    results = []
    timetable = parse_timetable()

    for ttb_party in timetable:
        party_name = timetable[ttb_party].get('id', ttb_party)

        if party in unidecode.unidecode(party_name).lower():
            for ttb_area in timetable[ttb_party].get('areas', []):
                area_selector = timetable[ttb_party]['areas'][ttb_area]
                area_name = area_selector.get('id', ttb_party)

                if area in unidecode.unidecode(area_name).lower():
                    result = {
                        'party': party_name,
                        'area': area_name,
                        'lineup': []
                    }

                    for dj in area_selector.get('dj', []):
                        result['lineup'].append({
                            'dj': dj.get('dj', ''),
                            'start': dj.get('start', ''),
                            'end': dj.get('end', '')
                        })

                    results.append(result)

    return results


""" --- Functions that control the bot's behavior --- """


def info(intent_request, info_key):
    info_data = parse_info()
    output_session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}

    return close(
        output_session_attributes,
        'Fulfilled',
        {
            'contentType': 'PlainText',
            'content': info_data.get(info_key, 'Could not find info on this, sorry!')
        }
    )


def weathertoday(intent_request):
    output_session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}

    url = 'http://api.openweathermap.org/data/2.5/weather?q=%s&units=metric&APPID=%s' % (
        os.environ.get('LOCATION', 'Biddinghuizen,The%20Netherlands'),
        os.environ.get('OPENWEATHER_API', '')
    )

    try:
        resp = requests.get(url=url)
        data = resp.json()
        message = '''
The current temperature in Biddinghuizen is {curr_temp}C. With a low of {low_temp}C and a high of {high_temp}C.

The weather will be mostly {weather_main}.'''.format(
            curr_temp=data.get('main', {}).get('temp', 'INVALID'),
            low_temp=data.get('main', {}).get('temp_min', 'INVALID'),
            high_temp=data.get('main', {}).get('temp_max', 'INVALID'),
            weather_main=data.get('weather', [])[0].get('main', '').lower())
        if 'precipitation' in data:
            message += '''

It will unfortunately be somewhat bad weather today, {value}mm will {mode} out of the sky.'''.format(
                value=data.get('precipitation', {}).get('value', '0.01'),
                mode=data.get('precipitation', {}).get('mode', 'rain'))
    except Exception as e:
        print(e)
        message = 'We could not fetch weather data at this time, please try again later.'

    return close(
        output_session_attributes,
        'Fulfilled',
        {
            'contentType': 'PlainText',
            'content': message
        }
    )


def upprevious(intent_request):
    output_session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}
    area = intent_request['currentIntent']['slots']['area'].replace('the', '').strip()

    result = locate_current_dj(area, previous_=True)
    if result:
        message = result
    else:
        message = '''
We could not locate a previous DJ. DefQon.1 might have not started yet, or has ended already.'''

    return close(
        output_session_attributes,
        'Fulfilled',
        {
            'contentType': 'PlainText',
            'content': message
        }
    )


def upnext(intent_request):
    output_session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}
    area = intent_request['currentIntent']['slots']['area'].replace('the', '').strip()

    result = locate_current_dj(area, next_=True)
    if result:
        message = result
    else:
        message = '''
We could not locate a DJ that will play in the next hour in that area. DefQon.1 might have not started yet, or has ended already.'''

    return close(
        output_session_attributes,
        'Fulfilled',
        {
            'contentType': 'PlainText',
            'content': message
        }
    )


def currentplaying(intent_request):
    output_session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}
    area = intent_request['currentIntent']['slots']['area'].replace('the', '').strip()

    result = locate_current_dj(area)
    if result:
        message = result
    else:
        message = 'We could not locate a DJ that is currently playing in that area.'

    return close(
        output_session_attributes,
        'Fulfilled',
        {
            'contentType': 'PlainText',
            'content': message
        }
    )


def weatherforecast(intent_request):
    output_session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}

    url = 'http://api.openweathermap.org/data/2.5/forecast?q=%s&units=metric&APPID=%s' % (
        os.environ.get('LOCATION', 'Biddinghuizen,The%20Netherlands'),
        os.environ.get('OPENWEATHER_API', '')
    )

    try:
        resp = requests.get(url=url)
        data = resp.json()
        message = 'Here is a sneak peek at the forecast for Biddinghuizen:\n\n'
        for item in data.get('list', [])[:15]:
            message += '{text}: {temp}C - {main_weather}\n'.format(
                text=item.get('dt_txt', ''),
                temp=item.get('main', {}).get('temp', '21'),
                main_weather=item.get('weather', [{}])[0].get('main', '').lower()
            )
    except Exception as e:
        print(e)
        message = 'We could not fetch weather data at this time, please try again later.'

    return close(
        output_session_attributes,
        'Fulfilled',
        {
            'contentType': 'PlainText',
            'content': message
        }
    )


def arealineup(intent_request):
    party = intent_request['currentIntent']['slots'].get('party', '').replace('the', '').strip()
    area = intent_request['currentIntent']['slots']['area'].replace('the', '').strip()
    results = locate_lineup_area(area, party)

    if results:
        message = ''

        for area in results[:1]:
            message += '{party} - {area}'.format(
                party=area.get('party', ''), area=area.get('area', ''))
            for dj in area.get('lineup', []):
                start_dt = datetime.datetime.strptime(dj.get('start', ''), '%b %d %Y %I:%M%p')
                end_dt = datetime.datetime.strptime(dj.get('end', ''), '%b %d %Y %I:%M%p')
                message += '\n{start} - {end}: {dj}'.format(
                    start=start_dt.strftime('%a %I:%M%p'),
                    end=end_dt.strftime('%a %I:%M%p'),
                    dj=dj.get('dj', ''))
    else:
        message = 'We could not find this area! Please try a different one'

    output_session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}

    return close(
        output_session_attributes,
        'Fulfilled',
        {
            'contentType': 'PlainText',
            'content': message
        }
    )


def djplaying(intent_request):
    dj = intent_request['currentIntent']['slots']['dj']
    results = locate_dj(dj)

    if results:
        message = 'Looks like we found your DJ, he/she will be playing at these times and locations:'

        for result in results:
            message += '\n\n{dj} is playing at the {party}: at {area}, from {start} to {end}.'.format(
                dj=result.get('dj', ''),
                party=result.get('party', 'DefQon.1'),
                area=result.get('area', ''),
                start=result.get('start', ''),
                end=result.get('end', ''))
    else:
        message = 'We could not find a time and date for this DJ, sorry! Please try another name or variation.'

    output_session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}

    return close(
        output_session_attributes,
        'Fulfilled',
        {
            'contentType': 'PlainText',
            'content': message
        }
    )


def bye(intent_request):
    name = 'dude'
    try:
        graph = facebook.GraphAPI(access_token=os.environ.get('FB_ACCESS_TOKEN'), version='2.7')
        fb_data = graph.get_object(id=intent_request['userId'])
        name = fb_data['first_name']
    except Exception as e:
        print(e)
        """Don't worry, be happy."""

    output_session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}

    return close(
        output_session_attributes,
        'Fulfilled',
        {
            'contentType': 'PlainText',
            'content': '''
Feel free to reach out at any time if you have other questions.

See you around, {}!
'''.format(name)
        }
    )


def hi(intent_request):
    name = 'dude'
    try:
        graph = facebook.GraphAPI(access_token=os.environ.get('FB_ACCESS_TOKEN'), version='2.7')
        fb_data = graph.get_object(id=intent_request['userId'])
        name = fb_data['first_name']
    except Exception as e:
        print(e)
        """Don't worry, be happy."""

    output_session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}

    return close(
        output_session_attributes,
        'Fulfilled',
        {
            'contentType': 'PlainText',
            'content': '''
Hey, {}! It sure is nice to meet you. Here's a list of things you can ask me:

What is the lineup for the red on Saturday?
Who is currently playing at the blue?
Who is playing next at the indigo?
What is the weather going to be like?
Will it rain tomorrow?
What is the drug policy?
What should I take with me on the camping?

I also know a few other things, but I'm sure you'll find that out yourself.

Have fun at DefQon.1!

'''.format(name)
        }
    )


""" --- Intents --- """


def dispatch(intent_request):
    """
    Called when the user specifies an intent for this bot.
    """

    logger.debug('dispatch userId=%s, intentName=%s', intent_request['userId'], intent_request['currentIntent']['name'])

    intent_name = intent_request['currentIntent']['name']

    # Dispatch to your bot's intent handlers
    if intent_name == 'Hi':
        return hi(intent_request)
    if intent_name == 'Bye':
        return bye(intent_request)
    if intent_name == 'DJPlaying':
        return djplaying(intent_request)
    if intent_name == 'AreaLineup':
        return arealineup(intent_request)
    if intent_name == 'TodaysWeather':
        return weathertoday(intent_request)
    if intent_name == 'ThreeDayWeatherForecast':
        return weatherforecast(intent_request)
    if intent_name == 'CurrentlyPlaying':
        return currentplaying(intent_request)
    if intent_name == 'UpNext':
        return upnext(intent_request)
    if intent_name == 'UpPrevious':
        return upprevious(intent_request)
    if 'Info' in intent_name:
        return info(intent_request, intent_name.replace('Info', ''))
    raise Exception('Intent with name ' + intent_name + ' not supported')


""" --- Main handler --- """


def lambda_handler(event, context):
    """
    Route the incoming request based on intent.
    The JSON body of the request is provided in the event slot.
    """
    os.environ['TZ'] = 'Europe/Amsterdam'
    time.tzset()
    logger.debug('event.bot.name=%s', event['bot']['name'])

    return dispatch(event)
