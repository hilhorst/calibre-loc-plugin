#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import, print_function)

__license__   = 'GPL v3'
__copyright__ = '2017, Nick Hilhorst'
__docformat__ = 'restructuredtext en'

import socket, re, datetime

from threading import Thread

from urllib import urlencode

from lxml import etree
from calibre.utils.icu import lower,upper
from calibre.utils.cleantext import clean_ascii_chars

from calibre.ebooks.metadata.book.base import Metadata

class Worker(Thread): # Get  details

	'''
	Get book details from Library of Congress in a separate thread
	http://lx2.loc.gov:210/lcdb?version=1.1&operation=searchRetrieve&query=bath.isbn=0385279302&startRecord=1&maximumRecords=5&recordSchema=mods
	'''
	name					= 'Worker'
	description				= _('Get book details from the Library of Congress in a separate thread')
	author					= 'Nick Hilhorst'
	version					= (0, 0, 1)
	minimum_calibre_version	= (0, 8, 0)

	BASE_URL = 'http://lx2.loc.gov:210/lcdb?'

	def __init__(self, query, result_queue, browser, log, relevance, plugin, timeout=20):
		Thread.__init__(self)
		self.daemon = True
		self.query = query
		self.result_queue =  result_queue
		self.log, self.timeout = log, timeout
		self.relevance, self.plugin = relevance, plugin
		self.browser = browser.clone_browser()

	def run(self):
		try:			
			self.get_details()
		except:
			self.log.exception('get_details failed for query: %r'%self.query)

	def get_details(self):
		try:
			self.namespaces = {'zs': 'http://www.loc.gov/zing/srw/','mods': 'http://www.loc.gov/mods/v3'}

			querydict = {
				'version': '1.1',
				'operation': 'searchRetrieve',
				'query': self.query,
				'startRecord': '1',
				'maximumRecords': '5',
				'recordSchema': 'mods'
			}
			self.url = self.BASE_URL + urlencode(querydict)

			response = self.browser.open_novisit(self.url, timeout=self.timeout)
			xml = response.read()
			if not xml:
				self.log.error('Failed to get result for query: %r'%self.query)
				return

		except Exception as e:
			if callable(getattr(e, 'getcode', None)) and e.getcode() == 404:
				self.log.error('URL malformed: %r'%self.url)
				return
			attr = getattr(e, 'args', [None])
			attr = attr if attr else [None]
			if isinstance(attr[0], socket.timeout):
				msg = 'LoC timed out. Try again later.'
				self.log.error(msg)
			else:
				msg = 'Failed to make details query: %r'%self.url
				self.log.exception(msg)
			return

		try:
			root = etree.fromstring(xml)
		except:
			msg = 'Failed to parse LoC details page: %r'%self.url
			self.log.exception(msg)
			return

		records = root.xpath('/zs:searchRetrieveResponse/zs:records/zs:record',namespaces=self.namespaces)
		self.log.info('records: %s'%(len(records)))
		if records:
			for record in records:
				self.parse_details(record)

	def parse_details(self, root):

		try:
			title = self.parse_title(root)
		except:
			self.log.exception('Error parsing title for query: %r'%self.query)
			title = None

		if not title:
			self.log.error('Could not find title for %r'%self.query)

		try:
			authors = self.parse_authors(root)
		except:
			self.log.exception('Error parsing authors for query: %r'%self.query)
			authors = []   

		if not authors:
			self.log.error('Could not find authors for %r'%self.query)
		
			return

		mi = Metadata(title, authors)
		
		try:
			isbn = self.parse_isbn(root)
			if isbn:
				# match 10 of 13 getallen aan het begin, gevolgd door een spatie of niets
				p = re.compile('^([0-9]{13}|[0-9]{10})(?= |\Z)')
				if isinstance(isbn, str):
					m = p.match(isbn)
					if m:
						mi.isbn = m.group()
				else:
					m = p.match(isbn[0])
					if m:
						mi.isbn = m.group()
		except:
			self.log.exception('Error parsing ISBN for url: %r'%self.url)

		try:
			lang = self.parse_language(root)
			if lang:
				mi.languages = lang
		except:
			self.log.exception('Error parsing language for url: %r'%self.url)

		try:
			lccn = self.parse_lccn(root)
			if lccn:
				if isinstance(lccn, str):
					mi.set_identifier('lccn',lccn)
				else:
					for identifier in lccn:
						mi.set_identifier('lccn',identifier)
		except:
			self.log.exception('Error parsing LCCN for url: %r'%self.url)

		try:
			ddc = self.parse_ddc(root)
			if ddc:
				if isinstance(ddc, str):
					mi.set_identifier('ddc',ddc)
				else:
					for identifier in ddc:
						mi.set_identifier('ddc',identifier)
		except:
			self.log.exception('Error parsing DDC for url: %r'%self.url)

		try:
			lcc = self.parse_lcc(root)
			if lcc:
				if isinstance(lcc, str):
					mi.set_identifier('lcc',lcc)
				else:
					for identifier in lcc:
						mi.set_identifier('lcc',identifier)
		except:
			self.log.exception('Error parsing LCC for url: %r'%self.url)

		mi.source_relevance = self.relevance

		self.result_queue.put(mi)
   
	def parse_title(self, root):
		titles = None
		titles = root.xpath('//ns:mods/ns:titleInfo/ns:title/text()', namespaces={'ns': 'http://www.loc.gov/mods/v3'})
		subtitles = None
		subtitles = root.xpath('//ns:mods/ns:titleInfo/ns:subTitle/text()', namespaces={'ns': 'http://www.loc.gov/mods/v3'})
		if titles:
			return " & ".join(titles)

	def parse_authors(self, root): 
		authors = None
		authors = root.xpath('//ns:mods/ns:name[@type=\'personal\']/ns:namePart[not(@*)]/text()', namespaces={'ns': 'http://www.loc.gov/mods/v3'})
		if authors:
			return authors

	def parse_isbn(self, root): 
		isbn = None
		isbn = root.xpath('//ns:mods/ns:identifier[@type=\'isbn\']/text()', namespaces={'ns': 'http://www.loc.gov/mods/v3'})
		if isbn:
			return isbn

	def parse_language(self, root): 
		lang = None
		lang = root.xpath('//ns:mods/ns:language/ns:languageTerm/text()', namespaces={'ns': 'http://www.loc.gov/mods/v3'})
		if lang:
			return lang

	def parse_lccn(self,root):
		lccn = None
		lccn = root.xpath('//ns:mods/ns:identifier[@type=\'lccn\']/text()', namespaces={'ns': 'http://www.loc.gov/mods/v3'})
		if lccn:
			return lccn

	def parse_ddc(self,root):
		ddc = None
		ddc = root.xpath('//ns:mods/ns:classification[@authority=\'ddc\']/text()', namespaces={'ns': 'http://www.loc.gov/mods/v3'})
		if ddc:
			return ddc

	def parse_lcc(self,root):
		lcc = None
		lcc = root.xpath('//ns:mods/ns:classification[@authority=\'lcc\']/text()', namespaces={'ns': 'http://www.loc.gov/mods/v3'})
		if lcc:
			return lcc
