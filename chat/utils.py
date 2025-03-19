import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

def fetch_link_preview(url):
    """Fetch metadata for a URL to create a link preview"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get title
        title = soup.title.string if soup.title else None
        
        # Get meta description
        description = None
        meta_desc = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
        if meta_desc:
            description = meta_desc.get('content')
            
        # Get image
        image = None
        meta_img = soup.find('meta', attrs={'property': 'og:image'})
        if meta_img:
            image = meta_img.get('content')
            # If relative path, make absolute
            if image and not urlparse(image).netloc:
                base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                image = f"{base_url}{image}" if image.startswith('/') else f"{base_url}/{image}"
                
        # Get site name
        site_name = None
        meta_site = soup.find('meta', attrs={'property': 'og:site_name'})
        if meta_site:
            site_name = meta_site.get('content')
        else:
            site_name = urlparse(url).netloc
            
        return {
            'url': url,
            'title': title,
            'description': description,
            'image': image,
            'site_name': site_name
        }
    except Exception as e:
        # Log error but don't crash
        print(f"Error fetching link preview: {str(e)}")
        return {
            'url': url,
            'title': None,
            'description': None,
            'image': None,
            'site_name': urlparse(url).netloc
        }