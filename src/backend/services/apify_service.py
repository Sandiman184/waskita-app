import requests
import os
from flask import current_app

class ApifyService:
    BASE_URL = "https://api.apify.com/v2"

    @staticmethod
    def get_token():
        return current_app.config.get('APIFY_API_TOKEN') or os.environ.get('APIFY_API_TOKEN')

    @staticmethod
    def get_actor_id(platform):
        # Map platform to Apify Actor ID using configuration (which falls back to env/defaults)
        actors = {
            'twitter': current_app.config.get('APIFY_TWITTER_ACTOR'),
            'tiktok': current_app.config.get('APIFY_TIKTOK_ACTOR'),
            'facebook': current_app.config.get('APIFY_FACEBOOK_ACTOR')
        }
        return actors.get(platform.lower())

    @staticmethod
    def start_scraping_job(platform, keywords, max_results=100, start_date=None, end_date=None, language='id', **kwargs):
        token = ApifyService.get_token()
        if not token:
            raise Exception("APIFY_API_TOKEN not configured")

        actor_id = ApifyService.get_actor_id(platform)
        if not actor_id:
            raise Exception(f"No Apify Actor configured for platform: {platform}")

        current_app.logger.info(f"Starting Apify job for platform: {platform}, Actor ID: {actor_id}")

        # Ensure actor_id uses ~ instead of / for API URL compatibility if needed, 
        # but standard API v2 usually accepts 'username/actorname' in path.
        # Actually for 'acts/{actorId}/runs', it prefers the actor ID or 'username~actorname'.
        # Let's try to fetch actor details first if possible or just use the format 'username~actorname'.
        
        # Safe replacement: / -> ~
        api_actor_id = actor_id.replace('/', '~')
        
        url = f"{ApifyService.BASE_URL}/acts/{api_actor_id}/runs?token={token}"
        
        # Prepare input based on platform/actor
        # This input structure varies by actor!
        # Assuming generic structure or specific known ones
        input_data = {}
        
        if platform.lower() == 'twitter':
            # kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest
            # Construct search term: "keyword lang:in since:date_from until:date_to"
            search_query = f"{keywords} lang:in"
            
            # Language handling: Enforce Indonesian (lang:in) or use provided if not 'id'/'in'
            # But per requirement: "hapus saja fungsi language gunakan lang:in atau in untuk bahasa indonesia"
            # So we enforce lang:in for now.
            
            # Note: If language param was passed and is NOT 'id', we might want to respect it, 
            # but user instruction says "hapus saja fungsi language", so we default to 'in'.
            # However, to be safe, if 'en' is explicitly requested (e.g. from legacy calls), we might break it?
            # User said: "akibat perubahan bahasa indonesia ke bahasa inggris sehingga fitur ini belum berfungsi"
            # and "hapus saja fungsi language gunakan lang:in".
            # So we will revert to using `lang:in` in the query.
            
            # Original code used: search_query = f"{keywords} lang:in"
            
            if start_date:
                search_query += f" since:{start_date}_00:00:00_UTC"
            if end_date:
                search_query += f" until:{end_date}_23:59:59_UTC"
            
            input_data = {
                "filter:blue_verified": False,
                "filter:consumer_video": False,
                "filter:has_engagement": False,
                "filter:hashtags": False,
                "filter:images": False,
                "filter:links": False,
                "filter:media": False,
                "filter:mentions": False,
                "filter:native_video": False,
                "filter:nativeretweets": False,
                "filter:news": False,
                "filter:pro_video": False,
                "filter:quote": False,
                "filter:replies": False,
                "filter:safe": False,
                "filter:spaces": False,
                "filter:twimg": False,
                "filter:videos": False,
                "filter:vine": False,
                "include:nativeretweets": False,
                "searchTerms": [
                    search_query
                ],
                "maxItems": max_results,
                "queryType": "Latest"
            }
             
        elif platform.lower() == 'tiktok':
            # clockworks/free-tiktok-scraper
            input_data = {
                "excludePinnedPosts": False,
                # "proxyCountryCode": None, # Removed to use default/auto
                "resultsPerPage": max_results, # Items per page
                "postNumber": max_results, # Limit total items (common parameter)
                "scrapeRelatedVideos": False,
                "shouldDownloadAvatars": False,
                "shouldDownloadCovers": False,
                "shouldDownloadMusicCovers": False,
                "shouldDownloadSlideshowImages": False,
                "shouldDownloadSubtitles": False,
                "shouldDownloadVideos": False
            }
            
            # Intelligent input mapping
            if keywords.strip().startswith('@'):
                # Handle as profile scraping
                input_data["profiles"] = [keywords.strip().lstrip('@')]
            elif ' ' in keywords.strip():
                # Handle as search query if contains spaces
                input_data["searchQueries"] = [keywords.strip()]
            else:
                # Handle as hashtag (default)
                clean_keyword = keywords.strip().lstrip('#')
                input_data["hashtags"] = [clean_keyword]
                # Also add as search query as fallback if hashtag yields few results? 
                # Better to be specific to avoid duplicates or confusion
                # input_data["searchQueries"] = [keywords.strip()] 
        
        elif platform.lower() == 'facebook':
            # powerai/facebook-post-search-scraper
            # This actor expects "query" (string) or "queries" (list)
            # and location_uid.
            # However, looking at the actor documentation, it might need specific format.
            # Assuming 'query' is the correct field for search keywords.
            
            # Hardcoded location_uid as per requirement (default 'id' means Indonesia or generic?)
            # Usually location_uid 'id' refers to Indonesia if that's the intention, 
            # but 'id' is also the ISO code. 
            # Let's ensure maxResults is passed correctly as 'maxResults' (camelCase)
            
            location_uid = 'id'
            recent_posts = kwargs.get('recent_posts', False)
            
            input_data = {
                "location_uid": location_uid,
                "query": keywords,
                "recent_posts": recent_posts,
                "maxResults": max_results,
                # Add typical parameters to ensure better results
                "language": "id_ID"
            }
        
        try:
            response = requests.post(url, json=input_data)
            response.raise_for_status()
            data = response.json()
            return data.get('data', {})
        except Exception as e:
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_msg = f"{str(e)} - Response: {e.response.text}"
                except:
                    pass
            current_app.logger.error(f"Apify start job error: {error_msg}")
            raise Exception(error_msg)

    @staticmethod
    def get_run_status(run_id):
        token = ApifyService.get_token()
        if not token:
            raise Exception("APIFY_API_TOKEN not configured")
            
        url = f"{ApifyService.BASE_URL}/actor-runs/{run_id}?token={token}"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get('data', {})
        except Exception as e:
            current_app.logger.error(f"Apify get status error: {str(e)}")
            raise

    @staticmethod
    def get_dataset_info(dataset_id):
        token = ApifyService.get_token()
        if not token:
            raise Exception("APIFY_API_TOKEN not configured")
            
        url = f"{ApifyService.BASE_URL}/datasets/{dataset_id}?token={token}"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get('data', {})
        except Exception as e:
            current_app.logger.error(f"Apify get dataset info error: {str(e)}")
            # Return None to indicate failure, distinguishing from empty dataset
            return None

    @staticmethod
    def get_dataset_items(dataset_id, limit=None, offset=None):
        token = ApifyService.get_token()
        if not token:
            raise Exception("APIFY_API_TOKEN not configured")
            
        # Use clean=false to ensure we get all fields including hidden ones if necessary
        # clean=true might hide fields that are important for mapping
        url = f"{ApifyService.BASE_URL}/datasets/{dataset_id}/items?token={token}&clean=false"
        
        if limit is not None:
            url += f"&limit={limit}"
        if offset is not None:
            url += f"&offset={offset}"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            # Apify sometimes returns list directly, sometimes inside 'data' wrapper depending on endpoint?
            # Actually /datasets/{id}/items usually returns a list of objects directly.
            if isinstance(data, list):
                return data
            return data.get('items', []) # Fallback if structure is different
        except Exception as e:
            current_app.logger.error(f"Apify get dataset items error: {str(e)}")
            raise

    @staticmethod
    def abort_run(run_id):
        token = ApifyService.get_token()
        if not token:
            raise Exception("APIFY_API_TOKEN not configured")
            
        url = f"{ApifyService.BASE_URL}/actor-runs/{run_id}/abort?token={token}"
        
        try:
            response = requests.post(url)
            response.raise_for_status()
            data = response.json()
            return data.get('data', {})
        except Exception as e:
            current_app.logger.error(f"Apify abort run error: {str(e)}")
            raise
