from sopel import module, tools, db
from sopel.config.types import StaticSection, ValidatedAttribute, ListAttribute, NO_DEFAULT
from sopel.formatting import color, bold
from sopel.tools.time import (
    format_time,
    get_channel_timezone,
    get_nick_timezone,
    get_timezone,
    validate_timezone
)

import requests
import urllib.parse
import pendulum

import re

LOGGER = None

class SpaceXSection(StaticSection):
    channel = ValidatedAttribute('channel', default=NO_DEFAULT)

def setup(bot):
    global LOGGER
    
    bot.config.define_section('spacex', SpaceXSection)

    bot.db.set_plugin_value("spacex", "nextlaunch", None)
    bot.db.set_plugin_value("spacex", "nextlaunch_date", None)
    bot.db.set_plugin_value("spacex", "nextlaunch_name", None)
    bot.db.set_plugin_value("spacex", "nextlaunch_webcast", None)

    LOGGER = tools.get_logger('spacex')

# from Supybot/Limnoria utils.str
def _normalizeWhitespace(s, removeNewline=True):
    r"""Normalizes the whitespace in a string; \s+ becomes one space."""
    if not s:
        return str(s) # not the same reference
    starts_with_space = (s[0] in ' \n\t\r')
    ends_with_space = (s[-1] in ' \n\t\r')
    if removeNewline:
        newline_re = re.compile('[\r\n]+')
        s = ' '.join(filter(bool, newline_re.split(s)))
    s = ' '.join(filter(bool, s.split('\t')))
    s = ' '.join(filter(bool, s.split(' ')))
    if starts_with_space:
        s = ' ' + s
    if ends_with_space:
        s += ' '
    if len(s) > 200:
        s = s[:199] + "…"
    return s

def is_tbd(ts):
    dt = pendulum.parse(ts)
    if dt.day == 1 and dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
        return True
    
    return False

def _parse_results(data, desc=None, idx=0, tz=None):
    # parses data from API

    timezones = {
        11: "US/Pacific",
        12: "US/Eastern",
    }

    try:
        tmp = data["results"][idx]
        data = requests.get(tmp['url']).json()
        # print(url)
    except:
        data = data["results"][idx]
    name = data['name'].strip()
    if "  " in name:
        name = name.split()
        name = " ".join(name)
    location = "{} ({})".format(data['pad']['name'], data['pad']['location']['name']) 
    loc_id = data['pad']['location']['id']
    tz = tz or timezones.get(loc_id) or "UTC"
    when = pendulum.parse(data['net']).in_tz(tz)
    status = data['status']['name']
    if "Go" in status:
        status = color(status, "green")
    if data['probability']:
        prob = f" ({data['probability']}%)" if data['probability'] > 0 else ""
    else:
        prob = ""
    try:
        # {data['mission']['name']} -> 
        mission = f"{_normalizeWhitespace(data['mission']['description'])}"
    except:
        mission = None

    landing = None
    rocket = None
    if data['pad']['agency_id'] == 121:
        # SpaceX Landing Attempt?
        rockets = data['rocket']['launcher_stage']
        if len(rockets) == 1:
            # Falcon 9 Block 5
            landing = rockets[0]['landing']['attempt']
            # reused = rockets[0]['reused']
            # if reused:
            rocket = "Flight #{} for this booster.".format(rockets[0]['launcher_flight_number'])
            if landing:
                landing = rockets[0]['landing']['description']
        else:
            # Falcon Heavy
            #TBD
            pass
    lines = []
    if status != "TBD":
        lines.append(f"\x02[Launch]\x02 {name} from {location} \x02[When]\x02 {color(when.format('MMM Do @ h:mm A zz'), 'cyan')} \x02[Status]\x02 {status}{prob}")
    else:
        lines.append(f"\x02[Launch]\x02 {name} from {location} \x02[When]\x02 {color(when.format('MMM Do @ h:mm A zz'), 'cyan')}")
    if mission: lines.append("\x02[Mission]\x02 " + mission)
    if data.get('vidURLs'):
        vid = " \x02[Watch]\x02 {}".format(', '.join(list(set(data['vidURLs']))))
        # vid = " \x02[Watch]\x02 {}".format(data['vidURLs'])
    else:
        vid = ""
    if when.diff(None, False).seconds < 0:
        stub = "-"
    else:
        stub = "+"
    if not vid: lines.append(f"\x02[Clock]\x02 T{stub}{when.diff().in_words()}{vid}")
    line = " ".join(lines)
    lines = []
    lines.append(line)
    if rocket:
        if landing:
            lines.append(rocket + " " + landing)
        else:
            lines.append(rocket)
    if vid: lines.append(f"\x02[Clock]\x02 T{stub}{when.diff().in_words()}{vid}")

    return lines

def _fetch_data(url):
    try:
        data = requests.get(url).json()
        if data:
            return data
        else:
            return None
    except:
        return None

def _fetch_launchpad(id):
    url = (f"https://api.spacexdata.com/v4/launchpads/{id}")
    return _fetch_data(url)

def _fetch_rocket(id):
    url = (f"https://api.spacexdata.com/v4/rockets/{id}")
    return _fetch_data(url)

def _fetch_landpad(id):
    url = (f"https://api.spacexdata.com/v4/landpads/{id}")
    return _fetch_data(url)

def _fetch_payload(id):
    url = (f"https://api.spacexdata.com/v4/payloads/{id}")
    return _fetch_data(url)

def _fetch_core(id):
    url = (f"https://api.spacexdata.com/v4/cores/{id}")
    return _fetch_data(url)

def _parse_results_spacex(data, desc=None, idx=0, tz=None):
    # parses data from API

    lines = []

    name = data['name']
    launch_time = pendulum.parse(data['date_utc'])
    from_now = launch_time - pendulum.now('UTC') 

    if (data['tbd'] or is_tbd(data['date_utc'])):
        if (launch_time.month > pendulum.now('UTC').month): 
            when = "sometime in {}".format(launch_time.format('MMMM'))
        else:
            when = "sometime this {}".format(data['date_precision'])
    else:
        if tz:
            launch_time_utc = launch_time.in_tz(tz).format('MMM Do, h:mmA zz')
        else:
            launch_time_utc = launch_time.in_tz('UTC').format('MMM Do, H:mm zz')

        launch_time_local = pendulum.parse(data['date_local']).format('MMM Do, h:mmA')
        from_now_human = launch_time.diff_for_humans()

        if data['net']:
            when = "NET {} ({} local)".format(launch_time_utc, launch_time_local)
        else:
            when = "at {} ({} local), which is {}".format(launch_time_utc, launch_time_local, from_now_human)

    launchpad_data = _fetch_launchpad(data['launchpad'])
    location = launchpad_data['name'] if launchpad_data else "Unknown"

    rocket_data = _fetch_rocket(data['rocket'])
    rocket = rocket_data['name'] if rocket_data else "Unknown"
    
    lines.append(f"\x02{name}:\x02 {rocket} launch from {location} {when}")

    cores = data['cores']
    if cores:
        for core in cores:
            core_data = _fetch_core(core['core'])
            serial = core_data['serial'] if core_data else "unknown"
            flight = core['flight']
            landing = "landing Unknown"
            if core['landing_attempt']:
                landing = "landing "
                if core['landing_type'] == "RTLS":
                    landing += "at "
                else:
                    landing += "on "

                landpad_data = _fetch_landpad(core['landpad'])
                if landpad_data:
                    landing += landpad_data['full_name']
                else:
                    landing = "landing Unknown"           

            lines.append(f"[First Stage] Core {serial}, flight #{flight} {landing}")
    else:
        lines.append(f"[First Stage] Unknown")

    payloads = data['payloads']
    for payload in payloads:
        payload_data = _fetch_payload(payload)
        if payload_data:
            p_id = payload_data['name']
            p_type = payload_data['type']
            p_orbit = payload_data['orbit']
            p_mass_kg = payload_data['mass_kg']
            p_customer = payload_data.get('customers')
            p_country = payload_data.get('nationalities')

            if (not p_customer or not p_country):
                customer = ""
            else:
                customer = f" for {p_customer[0]} of {p_country[0]}"

            if (p_mass_kg is None):
                weight = ""
            else:
                weight = " weighing "+str(p_mass_kg)+"kg"

            lines.append(f"[Payload] {p_id} {p_type}{weight} to {p_orbit}{customer}")

    if (not data['tbd']):
        if (from_now.in_hours() < 4):
            webcast = data.get('links').get('webcast') or "https://spacex.com/webcast"
            lines.append(f"[Webcast] {webcast}")

    return lines


@module.commands('launch')
@module.example('!launch')
def launch(bot, trigger):
    """Fetches next scheduled rocket launch."""

    args = trigger.group(2)
    if args: args = args.split()
    zone = None
    if args:
        tmp_args = args
        for idx,arg in enumerate(tmp_args):
            if arg.strip().lower() == "--utc":
                zone = "UTC"
                args.pop(idx)
    channel_or_nick = tools.Identifier(trigger.nick)
    zone = zone or get_nick_timezone(bot.db, channel_or_nick)
    if not zone:
        channel_or_nick = tools.Identifier(trigger.sender)
        zone = get_channel_timezone(bot.db, channel_or_nick)

    b_url = "https://spacelaunchnow.me/api/3.3.0/launch/upcoming/?format=json&limit=5"
    try:
        data = requests.get(b_url).json()
    except:
        return bot.reply("I couldn't fetch data from the API")
    
    if not data.get("results"):
        return bot.reply("No results returned from the API")

    if args:
        tmp_args = " ".join(args)
        try:
            parsed_data = _parse_results(data, idx=int(tmp_args.strip())-1, tz=zone)
        except:
            parsed_data = _parse_results(data, tz=zone)
    else:
        parsed_data = _parse_results(data, tz=zone)

    for line in parsed_data:
        bot.say(line, max_messages=2)

def fetch_spacex_data(idx=0):
    b_url = "https://api.spacexdata.com/v4/launches/upcoming?offset="+str(idx)+"&limit=1"
    try:
        data = requests.get(b_url).json()
        data = data[0]
    except:
        data = None

    return data

@module.commands('spacex')
@module.example('!spacex')
def spacex(bot, trigger):
    """Fetches next scheduled SpaceX rocket launch."""

    args = trigger.group(2)
    try:
        idx = int(args)
        if (idx < 0):
            idx = 0

        if (idx > 10):
            idx = 10
    except:
        idx = 0
 #   print(args)
 #   if args: args = args.split()
    zone = None
 #   if args:
 #       tmp_args = args
 #       for idx,arg in enumerate(tmp_args):
 #           if arg.strip().lower() == "--utc":
 #               zone = "UTC"
 #               args.pop(idx)
    channel_or_nick = tools.Identifier(trigger.nick)
    zone = zone or get_nick_timezone(bot.db, channel_or_nick)
    if not zone:
        channel_or_nick = tools.Identifier(trigger.sender)
        zone = get_channel_timezone(bot.db, channel_or_nick)

    data = fetch_spacex_data(idx)

    if not data:
        return bot.reply("No results returned from the API")

    parsed_data = _parse_results_spacex(data, "SpaceX", tz=zone)

    for line in parsed_data:
        bot.say(line, max_messages=2)

@module.interval(300)
def periodic_spacex(bot):
    global LOGGER
    data = fetch_spacex_data(0)

    if not data:
        return

    launch_time = pendulum.parse(data['date_utc'])
    if (data.get('tbd') or is_tbd(data['date_utc'])):
        if (launch_time.month > pendulum.now('UTC').month): 
            launch_date = "sometime in {}".format(launch_time.format('MMMM'))
        else:
            launch_date = "sometime this {}".format(data['date_precision'])
    else:
        launch_date = (f"{launch_time.format('MMM Do, H:mm zz')}")

    #topic_orig = bot.channels[tools.Identifier('#kyle')].topic
    topic_orig = bot.channels[tools.Identifier(bot.config.spacex.channel)].topic
    #print (f"Topic: [{topic_orig}]")
    if topic_orig.find('||') != -1:
        topic = topic_orig.split('||', 1)
        launch_info = (f" {data['name']}, {launch_date}")
        new_topic  = topic[0] + '||' + launch_info
        
        if topic_orig != new_topic:
            LOGGER.info(f"Topic Channged from [{topic_orig}] to [{new_topic}]")
            bot.write(('TOPIC', bot.config.spacex.channel + ' :' + new_topic))
            #bot.write(('TOPIC', '#kyle' + ' :' + new_topic))

    nextlaunch = bot.db.get_plugin_value("spacex", "nextlaunch")
    nextlaunch_date = bot.db.get_plugin_value("spacex", "nextlaunch_date")
    nextlaunch_name = bot.db.get_plugin_value("spacex", "nextlaunch_name")
    bot.say(f"periodic_spacex: [{nextlaunch}]=[{data['flight_number']}] [{nextlaunch_date}]=[{data['date_utc']}]", "#kyle")
    if (nextlaunch):
        line = None

        if (nextlaunch != data['flight_number']):
            line = (f"\x02[SpaceX Schedule Update]\x02 A new Mission has been scheduled next. Was: {nextlaunch_name} Now: {data['name']}") 
        elif (nextlaunch_date != data['date_utc']):
            line = (f"\x02[SpaceX Schedule Update]\x02 A new Launch Time has been established. Was: {pendulum.parse(nextlaunch_date).format('MMM Do, H:mm zz')} Now: {launch_date}") 
            
        if line:
            bot.say(line, bot.config.spacex.channel, max_messages=2)
            
            parsed_data = _parse_results_spacex(data, "SpaceX", tz="UTC")
            for line in parsed_data:
                bot.say(line, bot.config.spacex.channel, max_messages=2)

    bot.db.set_plugin_value("spacex", "nextlaunch", data['flight_number'])
    bot.db.set_plugin_value("spacex", "nextlaunch_date", data['date_utc'])
    bot.db.set_plugin_value("spacex", "nextlaunch_name", data['name'])
    webcast = data.get('links').get('webcast') or "https://spacex.com/webcast"
    bot.db.set_plugin_value("spacex", "nextlaunch_webcast", webcast)

@module.interval(5)
def periodic_time_check(bot):
    nextlaunch_date = bot.db.get_plugin_value("spacex", "nextlaunch_date")
    nextlaunch_name = bot.db.get_plugin_value("spacex", "nextlaunch_name")
    nextlaunch_webcast = bot.db.get_plugin_value("spacex", "nextlaunch_webcast")

    if (nextlaunch_date and not is_tbd(nextlaunch_date)):
        launchdate = pendulum.parse(nextlaunch_date).format('MMM Do, H:mm zz')
        delta = pendulum.parse(nextlaunch_date) - pendulum.now()
        delta = delta.in_seconds()

        #bot.say(f"periodic_time_check: [{launchdate}] [{delta}]", "#kyle")
        #topic = target.Channel('#spacex').topic
        #bot.say(f"{topic}", "#kyle")

        line = None
        if (delta < 3603 and delta > 3597):
            line = (f"\x02[Launch Alert]\x02 SpaceX launch of {nextlaunch_name} is scheduled to lift off in 1 hour at {launchdate}!")
        elif (delta < 1803 and delta > 1797):
            line = (f"\x02[Launch Alert]\x02 SpaceX launch of {nextlaunch_name} is scheduled to lift off in 30 minutes at {launchdate}!")
        elif (delta < 603 and delta > 597):
            line = (f"\x02[Launch Alert]\x02 SpaceX launch of {nextlaunch_name} is scheduled to lift off in 10 minutes at {launchdate}!")
        elif (delta < 63 and delta > 57):
            line = (f"\x02[Launch Alert]\x02 SpaceX launch of {nextlaunch_name} is scheduled to lift off in 1 minute at {launchdate}!")

        if (line):
            line += (f" Watch here: {nextlaunch_webcast}")
            bot.say(line, "#spacex", max_messages=2)

