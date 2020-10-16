from sopel import module, tools
from sopel.config.types import StaticSection, ValidatedAttribute, ListAttribute, NO_DEFAULT
from twython import TwythonStreamer
import html

api = None
myStream = None
myStreamListener = None
sopel_instance = None
firstStart = True
LOGGER = None

class TwitterSection(StaticSection):
    consumer_key = ValidatedAttribute('consumer_key', default=NO_DEFAULT)
    consumer_secret = ValidatedAttribute('consumer_secret', default=NO_DEFAULT)
    access_token = ValidatedAttribute('access_token', default=NO_DEFAULT)
    token_secret = ValidatedAttribute('token_secret', default=NO_DEFAULT)
    twitter_channel = ValidatedAttribute('twitter_channel', default=NO_DEFAULT)
    twitter_follow = ListAttribute('twitter_follow', strip=True, default=None)
    twitter_query = ListAttribute('twitter_query', strip=True, default=None)


def configure(config):
    config.define_section('twittertwython', TwitterSection, validate=False)
    config.twittertwython.configure_setting(
        'consumer_key', 'Enter your Twitter consumer key')
    config.twittertwython.configure_setting(
        'consumer_secret', 'Enter your Twitter consumer secret')
    config.twittertwython.configure_setting(
        'access_token', 'Enter your Twitter access token')
    config.twittertwython.configure_setting(
        'token_secret', 'Enter your Twitter access token secret')

def setup(bot):
    global LOGGER
    bot.config.define_section('twittertwython', TwitterSection)
    LOGGER = tools.get_logger('twittertwython')

class MyStreamer(TwythonStreamer):
    global sopel_instance
    global LOGGER

    def on_success(self, data):
        try:
            if not data['in_reply_to_status_id'] and not data['in_reply_to_user_id_str']:
                if not data['retweeted'] and 'RT @' not in data['text']:
                    text = data['text']
                    if (data['truncated']):
                        if (data.get('extended_tweet')):
                            text = data['extended_tweet'].get('full_text') or data['text']
                    
                    quoted_status = data.get('quoted_status')
                    if (quoted_status):
                        quote_text = quoted_status.get('text')
                        if (quoted_status.get('truncated')):
                            quoted_status_extended = quoted_status.get("extended_tweet")
                            if (quoted_status_extended):
                                quote_text = quoted_status_extended.get('full_text') or data['quoted_status']['text']

                        if (quoted_status.get('entities').get('urls')):
                            url = " - " + quoted_status.get('entities').get('urls')[0].get('url')
                        else:
                            url = ''

                    text = text.replace('\n', ' ')
                    text = text.strip()
                    text = html.unescape(text)               

                    message = ('\x02{name} (@{screen_name})\x02 {text}').format(
                                name=data['user']['name'],
                                screen_name=data['user']['screen_name'],
                                text=text)
                    sopel_instance.say(message, sopel_instance.config.twittertwython.twitter_channel)
        except:
            LOGGER.info(f"Unhandled Tweet: {data}")

    def on_error(self, status_code, data):
        LOGGER.error(f"Twitter ERROR: {status_code}")
    
@module.interval(100)
@module.thread(True)
def twitterThread(bot):
    global api
    global myStream
    global myStreamListener
    global sopel_instance
    global firstStart
    global LOGGER

    sopel_instance = bot

    if (firstStart):
        LOGGER.info("Twitter Stream Started for channel {}".format(bot.config.twittertwython.twitter_channel))
        firstStart = False
        # Authenticate to Twitter
        stream = MyStreamer(bot.config.twittertwython.consumer_key, bot.config.twittertwython.consumer_secret,
                    bot.config.twittertwython.access_token, bot.config.twittertwython.token_secret)
        
        try:
            if (bot.config.twittertwython.twitter_query):
                stream.statuses.filter(follow=bot.config.twittertwython.twitter_follow, track=bot.config.twittertwython.twitter_query)
            else:
                stream.statuses.filter(follow=bot.config.twittertwython.twitter_follow)
        except:
                stream.disconnect()
                LOGGER.error("Twiter Stream Error. Restarting.")
                firstStart = True

        LOGGER.info("Twitter Stream Stopped")
        firstStart = True