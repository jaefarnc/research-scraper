import scrapy
from .base_spider import BaseSpider
from ..items import PdfFilesItem

class NDSSSpider(BaseSpider):
    name = 'ndss'
    allowed_domains = ['ndss-symposium.org']
    start_urls = ['https://www.ndss-symposium.org/previous-ndss-symposia/']

    def __init__(self, conference: str = 'ndss', year: str = ''):
        BaseSpider.__init__(self, conference, year)
        if not year:
            raise ValueError("The 'year' argument is required. Usage: scrapy crawl ndss -a year=YYYY")
    
    def start_requests(self):
        for url in self.start_urls:
            self.logger.info(f'Start scraping {url} for {self.year}')
            yield scrapy.Request(url=url, callback=self.parse)
    
    def parse(self, response):
        """
        Step 1: Parse the main symposia page to find the link for the target year.
        """
        self.logger.info(f"Searching for year {self.year} on {response.url}")

        # Find the button/link for the specific year provided.
        # Based on: <a class="...button..." href="...">2025</a>
        year_link = response.xpath(f'//a[contains(@class, "wp-block-button__link") and normalize-space()="{self.year}"]/@href').get()
        self.logger.debug(f"Year link found with primary XPat: {year_link}")
        
        if year_link:
            self.logger.info(f"Found link for {self.year}: {year_link}")
            yield response.follow(
                year_link,
                callback=self.parse_year_page,
                meta={'year': self.year}
            )
        else:
            self.logger.error(f"Could not find a link for the year {self.year} on the main page.")

    def parse_year_page(self, response):
        """
        Step 2: On the year's main page, find the link to the "Accepted Papers" page.
        """
        self.logger.info(f"Searching for 'Accepted Papers' link on {response.url}")
        
        # Find the link that contains "Accepted Papers".
        # Based on: <a href="..."><strong>More details Accepted Papers</strong></a>
        accepted_papers_link = response.xpath('//a[strong[contains(text(), "Accepted Papers")]]/@href').get()

        if accepted_papers_link:
            yield response.follow(accepted_papers_link, callback=self.parse_paper_list, meta=response.meta)
        else:
            self.logger.warning(f"No 'Accepted Papers' link found on {response.url}. Assuming this is the paper list page and proceeding.")
            # If no link is found, assume we are already on the list page
            yield from self.parse_paper_list(response)


    def parse_paper_list(self, response):
        """
        Step 3: On the list of accepted papers, find the links to each individual paper's detail page.
        """
        self.logger.info(f"Parsing paper list on {response.url}")

        # Primary selector for newer years
        # Based on: <a class="paper-link-abs" href="..."><span>More Details</span></a>
        links = response.xpath('//a[@class="paper-link-abs"]/@href').getall()

        # Fallback selector for older years
        # Based on: <a href="..."><strong>Read More</strong></a>
        if not links:
            self.logger.info("Primary selector failed, trying fallback selector for older years.")
            links = response.xpath('//a[strong[text()="Read More"]]/@href').getall()

        if not links:
            self.logger.error(f"Could not find any paper detail links on {response.url}. Spider stopping.")
            return

        self.logger.info(f"Found {len(links)} paper links to follow.")
        for link in links:
            yield response.follow(link, callback=self.parse_paper_details, meta=response.meta)

    def parse_paper_details(self, response):
        """
        Step 4: On the final detail page, extract all information using fallback logic.
        """
        self.logger.info(f"Extracting details from {response.url}")

        # Title (very robust)
        # Based on: <meta property="og:title" content="...">
        title = response.xpath('//meta[@property="og:title"]/@content').get()

        # Authors (with fallback)
        # Based on: <p><strong>Miaomiao Wang...</strong></p> OR <p class="ndss_authors">...</p>
        authors = response.xpath('//p/strong/text()').get()
        if not authors or '(' not in authors: # Simple check to see if it's likely an author list
             authors_raw = response.xpath('//p[@class="ndss_authors"]//text()').getall()
             authors = ''.join(authors_raw).replace('Author(s):', '').strip()

        # Abstract (with fallback)
        # Based on <p> after authors OR <p> after <h2>Abstract:</h2>
        abstract_parts = response.xpath('//strong/following-sibling::p/text()').getall()
        if not abstract_parts:
            abstract_parts = response.xpath('//h2[contains(text(), "Abstract")]/following-sibling::p/text()').getall()
        abstract = ' '.join(p.strip() for p in abstract_parts)

        # PDF URL (with fallback)
        # Based on: <a class="...pdf-button..." or <p class="ndss_downloads">
        pdf_url = response.xpath('//a[contains(@class, "pdf-button")]/@href').get()
        if not pdf_url:
            pdf_url = response.xpath('//p[@class="ndss_downloads"]//a/@href').get()

        # Create and populate the final item
        item = PdfFilesItem()
        item['title'] = self.clean_quotes(title.replace('- NDSS Symposium', '').strip()) if title else ''
        item['authors'] = self.clean_html_tags(authors).strip() if authors else ''
        item['abstract'] = self.clean_extra_whitespaces(abstract) if abstract else ''
        item['abstract_url'] = response.url
        
        full_pdf_url = response.urljoin(pdf_url) if pdf_url else ''
        item['pdf_url'] = full_pdf_url
        item['file_urls'] = [full_pdf_url] if full_pdf_url else []
        item['source_url'] = 13 # A unique ID for NDSS

        yield item