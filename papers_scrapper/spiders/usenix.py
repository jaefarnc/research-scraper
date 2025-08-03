import re
from pathlib import Path
import scrapy
from .base_spider import BaseSpider
from ..items import PdfFilesItem


class UsenixSpider(BaseSpider):
    name = 'usenix'
    allowed_domains = ['usenix.org']
    start_urls = [
        'https://www.usenix.org/conference/usenixsecurity24/summer-accepted-papers',
        'https://www.usenix.org/conference/usenixsecurity24/fall-accepted-papers'
    ]

    def __init__(self, conference: str = '', year: str = ''):
        BaseSpider.__init__(self, conference, year)

    def start_requests(self):
        for url in self.start_urls:
            self.logger.info(f'Start scraping {url} for {self.year}')
            yield scrapy.Request(
                url=url, 
                callback=self.parse,
                dont_filter=True,
                meta={'dont_redirect': True}
            )

    def parse(self, response):
        self.logger.info(f'Successfully fetched page: {response.url}')
        self.logger.info(f'Response status: {response.status}')
        
        # Find all paper blocks
        papers = response.xpath('//article[contains(@class,"node-paper")]')
        self.logger.info(f'Found {len(papers)} paper blocks')
        
        if len(papers) == 0:
            self.logger.warning('No papers found! Checking page structure...')
            # Check if we can find any articles at all
            all_articles = response.xpath('//article')
            self.logger.info(f'Found {len(all_articles)} total articles')
            
            # Log some of the page content for debugging
            titles = response.xpath('//h2//text()').getall()[:5]
            self.logger.info(f'Sample titles found: {titles}')
        
        for paper in papers:
            title = paper.xpath('.//h2/a/text()').get()
            presentation_url = paper.xpath('.//h2/a/@href').get()
            
            self.logger.debug(f'Processing paper: {title}')
            
            # Extract authors from the people field
            authors_html = paper.xpath('.//div[contains(@class,"field-name-field-paper-people-text")]//p').get()
            authors = scrapy.Selector(text=authors_html).xpath('string(.)').get() if authors_html else ''
            
            # Extract abstract from description field
            abstract_html = paper.xpath('.//div[contains(@class,"field-name-field-paper-description-long")]//p').get()
            abstract = scrapy.Selector(text=abstract_html).xpath('string(.)').get() if abstract_html else ''

            if presentation_url:
                self.logger.info(f'Following presentation URL: {presentation_url}')
                yield response.follow(
                    presentation_url,
                    callback=self.parse_presentation,
                    meta={
                        'title': self.clean_html_tags(title) if title else '',
                        'authors': self.clean_html_tags(authors) if authors else '',
                        'abstract': self.clean_html_tags(abstract) if abstract else '',
                        'abstract_url': response.urljoin(presentation_url)
                    },
                    dont_filter=True
                )
            else:
                self.logger.warning(f'No presentation URL found for paper: {title}')

    def parse_presentation(self, response):
        self.logger.info(f'Processing presentation page: {response.url}')
        
        # Try meta tag first for PDF URL
        pdf_url = response.xpath('//meta[@name="citation_pdf_url"]/@content').get()
        if not pdf_url:
            # Fallback: look for PDF link in the final paper field
            pdf_url = response.xpath('//div[contains(@class,"field-name-field-final-paper-pdf")]//a/@href').get()
        
        if pdf_url:
            pdf_url = response.urljoin(pdf_url)
            self.logger.info(f'Found PDF URL: {pdf_url}')
        else:
            self.logger.warning(f'No PDF URL found for: {response.url}')

        item = PdfFilesItem()
        item['title'] = response.meta['title']
        item['authors'] = response.meta['authors']
        item['abstract'] = response.meta['abstract']
        item['abstract_url'] = response.meta['abstract_url']
        item['pdf_url'] = pdf_url if pdf_url else ''
        item['file_urls'] = [pdf_url] if pdf_url else []
        item['source_url'] = 12  # USENIX

        self.logger.info(f'Yielding item for: {item["title"]}')
        yield item