#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
						print_function)

__license__   = 'GPL v3'
__copyright__ = '2017, Nick Hilhorst'
__docformat__ = 'restructuredtext en'

import time

from calibre.ebooks.metadata import check_isbn
from calibre.ebooks.metadata.sources.base import Source
from calibre.utils.icu import lower
from calibre.utils.cleantext import clean_ascii_chars

class LoC(Source):

	name					= 'LoC'
	description				= _('Downloads metadata from the Library of Congress')
	author					= 'Nick Hilhorst'
	version					= (0, 0, 1)
	minimum_calibre_version	= (0, 8, 0)

	capabilities = frozenset(['identify'])
	touched_fields = frozenset(['title', 'authors', 'identifier:isbn', 'identifier:lcc', 'identifier:ddc', 'identifier:lccn', 'languages'])
	has_html_comments = False
	supports_gzip_transfer_encoding = False
	can_get_multiple_covers = False

	def identify(self, log, result_queue, abort, title=None, authors=None, identifiers={}, timeout=30):
	
		br = self.browser

		log.info('title:%s'%(title))

		queries = self.create_queries(log, title, authors, identifiers)	
		if queries is None:
			log.error('Insufficient metadata to construct query')
			return
		
		from calibre_plugins.LoC.worker import Worker
		
		workers = [Worker(query, result_queue, br, log, i, self) for  i, query in enumerate(queries)]	
		for w in workers:
			w.start()
			# Don't send all requests at the same time
			time.sleep(0.1)

		while not abort.is_set():
			a_worker_is_alive = False
			for w in workers:
				w.join(0.2)
				if abort.is_set():
					break
				if w.is_alive():
					a_worker_is_alive = True
			if not a_worker_is_alive:
				break

		return None

	def create_queries(self, log, title=None, authors=None, identifiers={}):

		queries = []
		isbn = check_isbn(identifiers.get('isbn', None))
		if isbn is not None:
			queries.append('bath.isbn=%s'%(isbn))
		else:
			queries.append('dc.title=%s and dc.author=%s'%(title, authors))
		return queries