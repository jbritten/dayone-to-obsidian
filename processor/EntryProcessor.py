import re

from config.config import Config


class EntryProcessor:
    additional_tags = []
    tag_prefix = ""
    default_filename = ""
    max_filename_length = 30  # Default value

    @classmethod
    def initialize(cls):
        cls.additional_tags = Config.get("ADDITIONAL_TAGS", [])
        cls.tag_prefix = Config.get("TAG_PREFIX", "")
        cls.default_filename = Config.get("DEFAULT_FILENAME", "")
        cls.max_filename_length = Config.get("MAX_FILENAME_LENGTH", 30)

    def __init__(self):
        self.entry_dict = {}  # Initialize dict in the constructor

    def add_entry_to_dict(self, entry):
        identifier = entry["identifier"]
        if identifier in self.entry_dict:
            raise ValueError(f"Identifier {identifier} already exists in the dictionary.")
        else:
            self.entry_dict[identifier] = entry

    def replace_entry_id_with_info(self, term):
        return self.get_entry_info(self.entry_dict[term.group(2)])

    def get_entry_info(self, entry):
        return str(entry)

    @staticmethod
    def get_location(entry: dict):
        if 'location' not in entry:
            return ""

        # Add location
        locations = []

        for locale in ['userLabel', 'placeName', 'localityName', 'administrativeArea', 'country']:
            if locale == 'placeName' and 'userLabel' in entry['location']:
                continue
            elif locale in entry['location']:
                locations.append(entry['location'][locale])
        location_in_dict = ", ".join(locations)
        return location_in_dict

    @staticmethod
    def get_coordinates(entry: dict):
        if 'location' in entry:
            coordinates = str(entry['location']['latitude']) + ',' + str(entry['location']['longitude'])
            return coordinates

    @staticmethod
    def get_location_coordinate(entry: dict):
        location = EntryProcessor.get_location(entry)
        coordinates = EntryProcessor.get_coordinates(entry)
        if coordinates in ['', [], None]:
            location_string = location
        else:
            location_string = '[' + location + '](geo:' + coordinates + ')'
        return location_string

    @staticmethod
    def get_duration(media_entry: dict):
        duration_seconds = int(media_entry["duration"])
        hours, remainder = divmod(duration_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return "{:02d}:{:02d}:{:02d}".format(hours, minutes, seconds)

    @staticmethod
    def get_weather(entry):
        weather = ""
        if 'weather' in entry:
            weather_entry = entry['weather']
            if 'temperatureCelsius' in weather_entry and 'conditionsDescription' in weather_entry:
                temperature = int(weather_entry['temperatureCelsius'])
                description = weather_entry['conditionsDescription']
                if 'location' in entry and 'localityName' in entry['location']:
                    weather_location = entry['location']['localityName']
                    weather += f"{weather_location} "
                weather += f"{temperature}°C {description}"
        return weather

    @staticmethod
    def get_tags(entry):
        tag_list = []

        tag_list.extend(EntryProcessor.additional_tags)
        if 'tags' in entry:
            for t in entry['tags']:
                if len(t) == 0:
                    continue
                tag_list.append("%s%s" % (EntryProcessor.tag_prefix, t.replace(' ', '-').replace('---', '-')))
            if entry['starred']:
                tag_list.append("%sstarred" % EntryProcessor.tag_prefix)

        if len(tag_list) > 0:
            return ", ".join(tag_list)

        return ""

    @staticmethod
    def get_title(entry):
        if 'text' not in entry:
            return EntryProcessor.default_filename

        entry_text = entry['text']
        
        # Split the text into lines
        lines = entry_text.split('\n')
        
        # Find the first line that doesn't start with ![]
        first_non_image_line = None
        for line in lines:
            if len(line) > 0 and not re.match(r"!\[\]", line):
                first_non_image_line = line
                break
                
        if first_non_image_line is None or len(first_non_image_line.strip()) == 0:
            return EntryProcessor.default_filename

        # Remove markdown headers
        title = re.sub(r"^#+\s*", "", first_non_image_line.strip())

        # Replace disallowed characters with spaces
        title = re.sub(r'[\\/:\*\?"<>|#^\[\]]', ' ', title).strip()

        # Apply max length after all other processing
        return title[:EntryProcessor.max_filename_length]

