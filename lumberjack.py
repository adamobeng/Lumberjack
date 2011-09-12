#!/usr/bin/python2
# TODO: Unit tests.

# == Introduction ==
# **lumberjack** is a Python script for making EPUB3 media overlays
# allows you to step through an input file (either the XHTML files
# contained within an EPUB file, or a single source TEI XML file) while playing
# the corresponding audio transcript, in order to synchronise the two.
# **lumbjerjack** produces as output an Audacity-format label file (extension '.txt'), which it can then
# transformed into the appropriate SMIL files for inclusion in an EPUB 3 book, 
# or a TEI XML <timeline> element for re-insertion into the source file.

# === Licence ===
# **lumberjack** is distributed under the MIT License. More information is
# available in the COPYING file.

# === Installation ===
# 1. Download the source from Github as a tarball, or clone the repository
# 2. Extract lumberjack.py and copy it to somethere useful
# 3. Optinally, add it to your $PATH, or alias it in your shell
# 4. Optionally, Have buttered scones for tea.

# === Dependencies ===

# * [Python (2)](http://www.python.org/download/)
# * [pygame](http://www.pygame.org/download.shtml)

# == Installation ==

# == Usage ==

# === Parameters ===

# **lumberjack** takes three obligatory command-line options:
		
#		lumberjack /path/to/book.extension /path/to/audio.m4a \
#		-smilpath= /path/to 
# OR	
#		lumberjack /path/to/book.epub /path/to/audio.m4a \
#		-timeline= /path/to/timeline.xml
#
#  If given -smilpath , **lumberjack** generates one SMIL file for each input HTML file
#  called 'htmlfilename.html.smil'
#  If given -timeline, **lumberjack** generates a single TEI XML file containg a <timeline>
#  element which describes the timeline.
#


# Unfortunately, pygame doesn't handle the AAC/M4A files included
# in EPUBs, so **lumberjack** also expects there to be an OGG
# file with the same name as the M4A file (e.g. 'audio.ogg').
# This is not ideal. Perhaps a future version will convert the
# file or something.

# **lumberjack** also takes optional arguments:

#		lumberjack book.epub audio.m4a \
#		--logto /path/to/logfile.log

# Absent these arguments, **lumberjack** will output a logfile called
# 'audio.m4a.log'

# **lumberjack** can also be called with:

#		lumberjack book.epub audio.m4a \
#		--smilpath /path/to/ \ 
#		--uselog /path/to/logfile.log

# in which case it doesn't enter interactive logging mode, and just converts# the log file to SMIL files

# === Input ===

# **lumberjack** expects to be given 
#  -  an EPUB2/3 format file OR a TEI XML format file
#  -  an AAC/M4A audio file (also, as noted above, an OGG audio
#  file with the same name)

#  The input file can either be an EPUB file, or a single TEI XML file.
#  If the input file is not a valid ZIP file (as EPUB should be), **lumberjack** assumes
#  it's XML.

#  Within the EPUB file, it expects to find a 'container.xml' file, which points to the
#  OPF file, which itself points to one or more XHTML files. In short, the EPUB should be valid.

#  In addition to being valid, the XHTML files in the EPUB should contain in which certain <div>s
#  (i.e. those to be logged) have 'id' attributes and belong to the class 'identifiable' 
#  WiTHIN the XML file, such <div>s must belong instead to the class "transcribable"
# TODO: make these classes user-selectable

#  Note: In the output XML or SMIL file, the path to the audio file is set to be directly
#  inside the 'OEBPS' (or whatever) folder, the same as the XHTML files.
#  you can edit the SMIL files manually to change this.
# TODO: add command line option to change this.
 
# === Output ===

#  Output is in three formats:

# * A logfile (with extension .txt) is generated during logging. This is a
# tsv (Tab-separated values) file, of the format
#  	Start Position	End Position	Element id	Element text	File name	File count
# this format is compatible with, and can be imported into Audacity (all fields after and
# including the third become the text of the label in Audacity).

# The log file is always produced, because the other output formats are only
# produced at the end of logging, and you don't want to lose all your work
# if your machine crashes before that happens.

# * SMIL files (with extension .smil). One file for each HTML file in
# the EPUB. This has the format specified in the
# [EPUB3 specification](http://idpf.org/epub/30/spec/epub30-mediaoverlays.html#sec-overlay-docs).
# In essence, there is one <par> element for each log, which links a
# section of text to a section of the audio file.

# * An XML file, of the TEI format, containing a single <timeline> element
# This file does not actually conform to the [TEI P5 spec](http://www.tei-c.org/Guidelines/P5/), because the 
# <when> elements have 'to' and 'from' attributes. The same effect could be acheived with
# valid TEI, making judicious use of the 'absolute' and 'duration' and 'since' attributes.

# === Logging ===

# * **lumberjack** displays the current loggable section on the screen

# * Press space to log the end of the section
# * Press q to quit
# * Press p to pause
# * Press any other key to log a warning to file, 
# along with the current timestamp

from xml.dom.minidom import parse
import os
from os import listdir
import string
import codecs
import argparse
import zipfile


import pygame.mixer as mixer
import pygame.time as time
import pygame.key as key
import pygame.event as event
import pygame
from pygame import KEYDOWN, K_SPACE, K_q, K_p

# Helper function which recursively extracts text from an XML node and its descendants
def flatten_node(node):
	#  This string must be UTF-8
	return_text = u''
	for child in node.childNodes:
		if child.nodeType == child.TEXT_NODE:
			return_text = return_text + child.nodeValue
		else:
			return_text = return_text + (flatten_node(child))
	return return_text


def get_audio_elements_xml(xml_path):
	xml_file = open(xml_path)
	container_dom = parse(xml_file)
	audio_elements = []
	divs = container_dom.documentElement.getElementsByTagName('div')
	for div in divs:
		#  For each div, get its attributes and the text it contains
		attributes = {div.attributes.item(x).nodeName: div.attributes.item(x).value for x in range(div.attributes.length)}
		node_value = flatten_node(div)
		
		# If the div has a class attribute
		if 'class' in attributes.keys():
			# And that class attribute is 'identifiable'
			if attributes['class'].find('transcribable') != -1:
				# Then add it to the list of attributes we're going to return
				audio_elements.append({'id' : attributes['id'], 'count': 0, 'file_name': xml_path, 'text' : node_value})
	return audio_elements

def get_audio_elements(input_path):
	#  Gets all the elements which could have corresponding audio from an EPUB folder
	#  Note: the EPUB must be unzipped, and input_path should be the root folder of the EPUB,
	#  i.e., the folder that contains the manifest file and META-INF folder
	
	#  Either an epub or an XML file can be passed to lumberjack.
	#  We need to work out which this is.

	try:
	# EPUBs are just zip files, so open it
		epub = zipfile.ZipFile(input_path)
	except zipfile.BadZipfile:
		xml = open(input_path)		
		return get_audio_elements_xml(input_path)
		 

	#  Per the spec, this file must be here
	# And it's pretty much the only file whose position we can be sure of
	container_file = epub.open('META-INF/container.xml')
	container_dom = parse(container_file) 	

	#  But the location of the rootfile (a.k.a .opf file) needs to be determined
	rootfile_element = container_dom.documentElement.getElementsByTagName('rootfile')[0] 
	rootfile_attributes = {rootfile_element.attributes.item(x).nodeName: rootfile_element.attributes.item(x).value for x in range(rootfile_element.attributes.length)}

	rootfile_path = rootfile_attributes['full-path'] # The path to the .opf content file
	
	rootfile = epub.open(rootfile_path)
	rootfile_dom = parse(rootfile)

	#  Now get a list of all items in the manifest
	items = {}
	for item in rootfile_dom.documentElement.getElementsByTagName('item'):
		# And the attributes of each item
		attributes = {item.attributes.item(x).nodeName: item.attributes.item(x).value for x in range(item.attributes.length)}
		#  Of those attributes, let's keep track of the id and href
		items[attributes['id']] = attributes['href'] 
	
	#  Now we're going to try to get file names for the content XHTML files
	file_names = [] 
	for itemref in rootfile_dom.documentElement.getElementsByTagName('itemref'): # They're stored in itemref elements
		attributes = {itemref.attributes.item(x).nodeName: itemref.attributes.item(x).value for x in range(itemref.attributes.length)}

		file_name = items[attributes['idref']] #  Now, find the id of the element, and get the href of the id of the element. Whew!
		file_names.append(file_name)

	
	audio_elements = []
	for count, file_name in enumerate(file_names):
		# Remember, an EPUB is a zip file (and epub is a zipfile.ZipFile)
		html_file = epub.open(os.path.join(os.path.dirname(rootfile_path), file_name))
		dom = parse(html_file)

		# Get all the divs from the document
		divs = dom.documentElement.getElementsByTagName('div')
		for div in divs:
			#  For each div, get its attributes and the text it contains
			attributes = {div.attributes.item(x).nodeName: div.attributes.item(x).value for x in range(div.attributes.length)}
			node_value = flatten_node(div)

			# If the div has a class attribute
			if 'class' in attributes.keys():
				# And that class attribute is 'identifiable'
				if attributes['class'].find('identifiable') != -1:
					# Then add it to the list of attributes we're going to return
					audio_elements.append({'id' : attributes['id'],  'text' : node_value, 'count' : count, 'file_name' : file_name})

	return audio_elements


# Interactive, pygame-based logging function
#  Don't use mp3s
def log(audio_elements, log_file_path, audio_file, start_pos=0, resume=False):
#  Helper functions

	def advance(to, pos, prev_pos):
#  Actually do the logging
#  Get our position in the audio file and the current audio_element (a.k.a. the div in the TEI file)
		audio_element = audio_elements[to]

# Tell us what's going on
		print 'logged at time:', pos, 'count:', count 
		print '\t', audio_elements[to+1]['text'], '(file', audio_elements[to+1]['file_name'], ')'

# TEI XML files can have unicode, don'tchaknow
# The values of text_audio_element are being put into the correct order
		text_audio_element = map(unicode, [audio_element['id'], audio_element['text'], audio_element['file_name'], audio_element['count']])

# Convert to tab-separated
		tabbed_audio_element = string.join(text_audio_element, '\t')

# Remove line breaks
		no_line_breaks = tabbed_audio_element.replace ('\n', ' ')

#  And write it to the file
		log.write(str(prev_pos) + '\t' + str(pos) + '\t' + no_line_breaks  + '\n')

		return

# Print a warning message to the log file
# This contains four words so that the make_ functions don't throw a wobbly
# when trying to parse a logfile with error messages
	def warn(warning_message = ['DANGER,', 'WILL', 'ROBINSON,', 'DANGER!']):
# Pretty much as in advance()
# Audacity format requires seconds rather than miliseconds
		pos = mixer.music.get_pos()/1000
		log.write(str(pos) + '\t' + str(pos)  + '\t'  + string.join(warning_message, '\t') +'\n')
		print warning_string, pos

		return

	count = 0
	log = codecs.open(log_file_path, 'w', 'utf-8')
	paused = False
	prev_pos = 0
	pos = 0

# Initialise pygame
	pygame.init()
	screen = pygame.display.set_mode((100,100))
	mixer.music.load(audio_file)
	mixer.music.play(0, start_pos)
	mixer.init()
	event.set_grab(True)

# Print some startup info
	print "lumberjack: starting to log"
	print "Press space to log the end of the section displayed on the screen"
	print "Press q to quit"
	print "Press p to pause"
	print "Press any other key to log a warning to file, along with the current timestamp\n"
# Print some info about the first audio_element
	print '\t', audio_elements[0]['text'], '(', audio_elements[0], ')'

# Main logging loop
	while True:
		if not key.get_focused(): 
			mixer.music.pause()
			while (not key.get_focused()):
				time.wait(100)
				print "Waiting"
			mixer.music.unpause()

		else:
			keydown = [e for e in event.get() if event.type == KEYDOWN]
			for e in keydown:
				if e.key == K_SPACE:
					prev_pos = pos
					pos = mixer.music.get_pos()
					advance(count, pos, prev_pos)
					count = count + 1
				elif e.key == K_q: 
					return
				elif  e.key == K_p:
					if not paused:
						mixer.music.pause()
					else:
						mixer.music.unpause()
					#paused = !paused
					paused = not paused
				else:
					warn()

def make_smil(log_file, smil_path, audio_file):
	log_entries = open(log_file).readlines()

	# For each filename, we're going to write a SMIL file,
	# So get a list of all the filenames
	#  Split into a list based on the tab separations
	filenames = [string.split(log_entry, '\t')[4] for log_entry in log_entries]
	#  Remove the "filename" for error messages
	actual_filenames = [filename for filename in filenames  if filename[4]!= 'ROBINSON,']
	#  We only want one of each filename
	unique_filenames = list(set(actual_filenames))

	#  
	for smil_file in unique_filenames:
		f = open(smil_path + smil_file + '.smil', 'w')
		f.write('')
		f.close()

		#  Write the bit of the SMIL file that comes before the entries
		#  Yes, it's a hack.
		f = open(smil_path + smil_file + '.smil', 'a')
		f.write('<smil xmlns="http://www.w3.org/ns/SMIL" version="3.0" profile="http://www.ipdf.org/epub/30/profile/content/">\n <body> \n')

	#  Each clip has an id attribute of the form 'audio-filename-N', where N is
	#  the number of the clip in the file
		log_entries_in_this_file = [log_entry for log_entry in log_entries if string.split(log_entry, '\t')[4] == smil_file]
		for clip_id, log_text in enumerate(log_entries_in_this_file):
	#  Because it's a tsv file
			log = log_text.split('\t')

	#  Warnings in the logfile are detected because their third column is 'DANGER,'
			if log[2] != 'DANGER,':
				log_id, log_file_path, clip_begin, clip_end = log[2], log[4], log[0], log[1]
				f.write('<par id="%s"> <text src="%s"/> <audio src="%s" clipBegin="%ss" clipEnd="%ss"/> </par>\n' % ('audio-' + smil_file[:-5] + '-' + str(clip_id), log_file_path + '#' + log_id, os.path.basename(audio_file), clip_begin, clip_end))
			else:
				print "Invalid log", log_text
	#		print clip_id, log


		f.write('\n </body> \n </smil>')
		f.close()

def make_tei(log_file, smil_path, audio_file):
	log_entries = open(log_file).readlines()

	# This time, we're going to write a single XML file

	f = open(smil_path, 'w')
	f.write('')
	f.close()

	#  Write the bit of the XML file that comes before the entries
	#  Yes, it's (still) a hack.
	f = open(smil_path, 'a')
	f.write('<TEI>\n <timeline xml:id="timeline" unit="s" corresp="%s"> \n' % audio_file)

#  Each clip has an id attribute of the form 'audio-filename-N', where N is
#  the number of the clip in the file
	for clip_id, log_text in enumerate(log_entries):
#  Because it's a tsv file
		log = log_text.split('\t')

#  Warnings in the logfile are detected because their third column is 'DANGER,'
		if log[2] != 'DANGER,':
			log_id, log_file_path, clip_begin, clip_end = log[2], log[4], log[0], log[1]
			f.write('<when xml:id="%s" corresp="#%s" from="%s" to="%s"/>\n' % ('audio-'+ str(clip_id), log_id, clip_begin, clip_end))
		else:
			print "Invalid log", log_text
#		print clip_id, log


	f.write('\n </timeline> \n </TEI>')
	f.close()


def main():
	# Setup a parser for command-line arguments
	parser = argparse.ArgumentParser(description="Produce a smil file linking positions in an audio file to sections of an EPUB")
	parser.add_argument('input')
	parser.add_argument('audio')
	parser.add_argument('--smilpath')
	parser.add_argument('--timeline')
	parser.add_argument('--logto')
	parser.add_argument('--uselog')

	args = parser.parse_args()
	input = args.input
	audio_file = args.audio
	smil_path = args.smilpath
	timeline = args.timeline
	log_to = args.logto
	smil_file = args.smilpath
	use_log = args.uselog

	#  If filenames for the log file has not been provided, choose one
	if not log_to: log_to = audio_file + '.txt'

	#  Get the <div>s susceptible of being logged
	audio_elements = get_audio_elements(input)

	 #  ogg file because pygame doesn't support m4a
	ogg_file = audio_file[:-3] + 'ogg' 

	# If an existing log file has been provided
	if use_log:
		#  Just make the SMIL file based on it
		log_to = use_log
	else:
		# Otherwise, begin the interactive logging process
		log(audio_elements, log_to, ogg_file)

	# Either way make the SMIL/XML file based on the log file
	if smil_path:
		make_smil(log_to, smil_path, audio_file)
	elif timeline:
		make_tei(log_to, timeline, audio_file)


# Run the script
if __name__ == "__main__":
	main()

# Documentation generated using [Pycco](http://fitzgen.github.com/pycco/)

#  == References ==

#  http://docs.python.org/library/argparse.html#module-argparse
#  http://docs.python.org/tutorial/inputoutput.html
#  http://infohost.nmt.edu/tcc/help/pubs/lang/pytut/str-format.html
#  http://docs.python.org/library/string.html
#  http://docs.python.org/library/functions.html#map
#  http://www.evanjones.ca/python-utf8.html
#  http://www.java2s.com/Open-Source/Python/Game-2D-3D/Pygame/pygame-1.9.1release/examples/sound.py.htm
#  http://stackoverflow.com/questions/934160/write-to-utf-8-file-in-python
#  http://www.pygame.org/docs/ref/examples.html#pygame.examples.scroll.main
#  https://secure.wikimedia.org/wikipedia/en/wiki/Switch_statement#Python
#  http://docs.python.org/tutorial/controlflow.html
# http://docs.python.org/library/stdtypes.html
# http://www.velocityreviews.com/forums/t639597-append-a-new-value-to-dict.html
# http://docs.python.org/library/os.path.html
# http://docs.python.org/library/string.html
# http://stackoverflow.com/questions/1412004/reading-xml-using-python-minidom-and-iterating-over-each-node
#  http://docs.python.org/library/zipfile.html
# http://docs.python.org/library/os.path.html#module-os.path

