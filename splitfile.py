import logging
import sys
import traceback
import dateutil.parser
import pytz  # pip install pytz
import os
import shutil
import time
import json
import re
import subprocess
import platform

from processor.AudioEntryProcessor import AudioEntryProcessor
from processor.EntryProcessor import EntryProcessor
from processor.PdfEntryProcessor import PdfEntryProcessor
from processor.PhotoEntryProcessor import PhotoEntryProcessor
from processor.VideoEntryProcessor import VideoEntryProcessor
from config.config import Config


def rename_media(root, subpath, media_entry, filetype):
    pfn = os.path.join(root, subpath, '%s.%s' % (media_entry['md5'], filetype))
    if os.path.isfile(pfn):
        newfn = os.path.join(root, subpath, '%s.%s' % (media_entry['identifier'], filetype))
        print('Renaming %s to %s' % (pfn, newfn))
        os.rename(pfn, newfn)


def iso_to_timestamp(iso_date_str):
    """Convert ISO format date string to Unix timestamp."""
    if not iso_date_str:
        return None
    dt = dateutil.parser.isoparse(iso_date_str)
    return dt.timestamp()


def set_creation_date_macos(filepath, creation_date):
    """Set the creation date of a file on macOS using setfile command."""
    try:
        # Convert timestamp to the format setfile expects: MM/DD/YYYY HH:MM:SS
        date_str = time.strftime("%m/%d/%Y %H:%M:%S", time.localtime(creation_date))
        subprocess.run(['setfile', '-d', date_str, filepath], check=True)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"Warning: Could not set creation date for {filepath}: {str(e)}")


# Load the configuration
Config.load_config("config.yaml")
DEFAULT_TEXT = Config.get("DEFAULT_TEXT", "")

# Initialize the EntryProcessor class variables
EntryProcessor.initialize()

# Set this as the location where your Journal.json file is located
root = Config.get("ROOT")
icons = False  # Set to true if you are using the Icons Plugin in Obsidian

# name of folder where journal entries will end up
journalFolder = os.path.join(root, Config.get("JOURNAL_FOLDER"))
fn = os.path.join(root, Config.get("JOURNAL_JSON"))

# Clean out existing journal folder, otherwise each run creates new files
if os.path.isdir(journalFolder):
    print("Deleting existing folder: %s" % journalFolder)
    shutil.rmtree(journalFolder)
# Give time for folder deletion to complete. Only a problem if you have the folder open when trying to run the script
time.sleep(2)

if not os.path.isdir(journalFolder):
    print("Creating journal folder: %s" % journalFolder)
    os.mkdir(journalFolder)

if icons:
    print("Icons are on")
    dateIcon = "`fas:CalendarAlt` "
else:
    print("Icons are off")
    dateIcon = ""  # make 2nd level heading

print("Begin processing entries")
count = 0
with open(fn, encoding='utf-8') as json_file:
    data = json.load(json_file)

    photo_processor = PhotoEntryProcessor()
    audio_processor = AudioEntryProcessor()
    video_processor = VideoEntryProcessor()
    pdf_processor = PdfEntryProcessor()

    # Create a dictionary of all entries for link conversion
    entries_dict = {}
    for entry in data['entries']:
        if 'uuid' in entry:
            entries_dict[entry['uuid']] = entry

    for entry in data['entries']:
        newEntry = []

        createDate = dateutil.parser.isoparse(entry['creationDate'])
        localDate = createDate.astimezone(
            pytz.timezone(entry['timeZone']))  # It's natural to use our local date/time as reference point, not UTC

        coordinates = ''

        frontmatter = f"---\n" \
                      f"date: {localDate.strftime("%Y-%m-%d")}\n" \
                      f"time: {localDate.strftime("%Y-%m-%dT%H:%M:%S")}\n" \
                      f"created: {entry['creationDate']}\n"

        if 'modifiedDate' in entry:
            frontmatter += f"modified: {entry['modifiedDate']}\n"

        weather = EntryProcessor.get_weather(entry)
        if len(weather) > 0:
            frontmatter += f"weather: {weather}\n"
        tags = EntryProcessor.get_tags(entry)
        if len(tags) > 0:
            frontmatter += f"tags: {tags}\n"

        if 'location' in entry:
            coordinates = EntryProcessor.get_coordinates(entry)
            frontmatter += f"latitude: {entry['location']['latitude']}\n"
            frontmatter += f"longitude: {entry['location']['longitude']}\n"
            if 'country' in entry['location']:
                frontmatter += f"country: {entry['location']['country']}\n"
            if 'localityName' in entry['location']:
                frontmatter += f"city: {entry['location']['localityName']}\n"

        frontmatter += "locations: \n"
        frontmatter += "---\n"

        newEntry.append(frontmatter)

        # If you want time as entry title, uncomment below.
        # Add date as page header, removing time if it's 12 midday as time obviously not read
        # if sys.platform == "win32":
        #     newEntry.append(
        #         '## %s%s\n' % (dateIcon, localDate.strftime("%A, %#d %B %Y at %#I:%M %p").replace(" at 12:00 PM", "")))
        # else:
        # newEntry.append('## %s%s\n' % (
        #     dateIcon, localDate.strftime("%A, %-d %B %Y at %-I:%M %p").replace(" at 12:00 PM", "")))  # untested

        # Add body text if it exists (can have the odd blank entry), after some tidying up
        try:
            if 'text' in entry:
                newText = entry['text'].replace("\\", "")
            else:
                newText = DEFAULT_TEXT
            newText = newText.replace("\u2028", "\n")
            newText = newText.replace("\u1C6A", "\n\n")

            # Convert Day One internal links to Obsidian Wikilinks
            newText = EntryProcessor.convert_dayone_links(newText, entries_dict)

            if 'photos' in entry:
                # Correct photo links. First we need to rename them. The filename is the md5 code, not the identifier
                # subsequently used in the text. Then we can amend the text to match. Will only to rename on first run
                # through as then, they are all renamed.
                # Assuming all jpeg extensions.
                photo_list = entry['photos']
                for p in photo_list:
                    photo_processor.add_entry_to_dict(p)
                    rename_media(root, 'photos', p, p['type'])

                # Now to replace the text to point to the file in obsidian
                newText = re.sub(r"(\!\[\]\(dayone-moment:\/\/)([A-F0-9]+)(\))",
                                 photo_processor.replace_entry_id_with_info,
                                 newText)

            if 'audios' in entry:
                audio_list = entry['audios']
                for p in audio_list:
                    audio_processor.add_entry_to_dict(p)
                    rename_media(root, 'audios', p, "m4a")

                newText = re.sub(r"(\!\[\]\(dayone-moment:\/audio\/)([A-F0-9]+)(\))",
                                 audio_processor.replace_entry_id_with_info, newText)

            if 'pdfAttachments' in entry:
                pdf_list = entry['pdfAttachments']
                for p in pdf_list:
                    pdf_processor.add_entry_to_dict(p)
                    rename_media(root, 'pdfs', p, p['type'])

                newText = re.sub(r"(\!\[\]\(dayone-moment:\/pdfAttachment\/)([A-F0-9]+)(\))",
                                 pdf_processor.replace_entry_id_with_info, newText)

            if 'videos' in entry:
                video_list = entry['videos']
                for p in video_list:
                    video_processor.add_entry_to_dict(p)
                    rename_media(root, 'videos', p, p['type'])

                newText = re.sub(r"(\!\[\]\(dayone-moment:\/video\/)([A-F0-9]+)(\))",
                                 video_processor.replace_entry_id_with_info, newText)

            newEntry.append(newText)

        except Exception as e:
            logging.error(f"Exception: {e}")
            logging.error(traceback.format_exc())
            pass

        ## Start Metadata section

        newEntry.append('\n\n---\n')

        # Add location
        location = EntryProcessor.get_location_coordinate(entry)
        if not location == '':
            newEntry.append(location)

        # Add GPS, not all entries have this
        # try:
        #     newEntry.append( '- GPS: [%s, %s](https://www.google.com/maps/search/?api=1&query=%s,%s)\n' % ( entry['location']['latitude'], entry['location']['longitude'], entry['location']['latitude'], entry['location']['longitude'] ) )
        # except KeyError:
        #     pass

        # Save entries based on configuration
        use_date_folders = Config.get("USE_DATE_FOLDERS", True)  # Default to True for backward compatibility
        title = EntryProcessor.get_title(entry)
        date_str = localDate.strftime('%Y-%m-%d')

        if use_date_folders:
            # Save entries organised by year, year-month folders
            yearDir = os.path.join(journalFolder, str(createDate.year))
            monthDir = os.path.join(yearDir, createDate.strftime('%Y-%m'))

            if not os.path.isdir(yearDir):
                os.mkdir(yearDir)

            if not os.path.isdir(monthDir):
                os.mkdir(monthDir)
            
            target_dir = monthDir
        else:
            # Save all entries directly in journal folder
            target_dir = journalFolder

        # First try with just the title
        fnNew = os.path.join(target_dir, f"{title}.md")

        # If file exists, append the date
        if os.path.isfile(fnNew):
            fnNew = os.path.join(target_dir, f"{title} {date_str}.md")

            # If that still exists, start appending letters
            if os.path.isfile(fnNew):
                index = 97  # ASCII a
                fnNew = os.path.join(target_dir, f"{title} {date_str} {chr(index)}.md")
                while os.path.isfile(fnNew):
                    index += 1
                    fnNew = os.path.join(target_dir, f"{title} {date_str} {chr(index)}.md")

        with open(fnNew, 'w', encoding='utf-8') as f:
            for line in newEntry:
                f.write(line)
        
        # Set file timestamps based on creation and modification dates
        creation_ts = iso_to_timestamp(entry['creationDate'])
        modified_ts = iso_to_timestamp(entry.get('modifiedDate', entry['creationDate']))
        
        # Set modification and access times
        os.utime(fnNew, (creation_ts, modified_ts))
        
        # On macOS, also set the creation time
        if platform.system() == 'Darwin':  # Check if we're on macOS
            set_creation_date_macos(fnNew, creation_ts)

        count += 1

print("Complete: %d entries processed." % count)
