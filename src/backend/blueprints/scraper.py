from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from models.models import db, RawDataScraper, Dataset
from datetime import datetime
from utils.utils import get_jakarta_time, generate_activity_log
import uuid
import re

scraper_bp = Blueprint('scraper', __name__)

@scraper_bp.route('/scraper', methods=['GET', 'POST'])
@login_required
def index():
    """Scraper index page"""
    if request.method == 'POST':
        platform = request.form.get('platform')
        keyword = request.form.get('keyword')
        max_results = request.form.get('max_results', 25, type=int)
        
        if not platform or not keyword:
            flash('Platform and keyword must be filled', 'error')
            return redirect(request.url)
            
        try:
            # Create Dataset record
            new_dataset = Dataset(
                name=f"Scraping {platform.title()} - {keyword}",
                description=f"Scraping data from {platform} with keyword '{keyword}' on {get_jakarta_time().strftime('%Y-%m-%d %H:%M')}",
                uploaded_by=current_user.id,
                status='Raw',
                total_records=0
            )
            db.session.add(new_dataset)
            db.session.flush()
            
            # Since we don't have the actual scraper, we'll just log this action
            # and maybe create a dummy record if needed, but for now just the dataset entry is enough
            # to show it in the management table.
            
            db.session.commit()
            
            flash(f'Scraping job for "{keyword}" on {platform} successfully scheduled.', 'success')
            return redirect(url_for('dataset.management_table'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating scraping job: {str(e)}', 'error')
            return redirect(request.url)

    return render_template('data/scraping.html')

@scraper_bp.route('/scraping', methods=['GET'])
@login_required
def legacy_index():
    """Legacy route for scraping page"""
    return redirect(url_for('scraper.index'))

from services.apify_service import ApifyService

@scraper_bp.route('/start_scraping', methods=['POST'])
@login_required
def start_scraping():
    data = request.get_json() or {}
    platform = data.get('platform')
    keywords = data.get('keywords')
    max_results = data.get('max_results') or 25
    language = data.get('language') or 'id'  # Default to 'id' if not provided
    
    if not platform or not keywords:
        return jsonify({'success': False, 'message': 'Platform and keyword must be filled'}), 400
    
    # Validate platform
    if platform.lower() not in ['twitter', 'tiktok', 'facebook']:
        return jsonify({'success': False, 'message': 'Platform not supported. Only Twitter, TikTok, and Facebook are available.'}), 400
        
    try:
        new_dataset = Dataset(
            name=f"Scraping {str(platform).title()} - {keywords}",
            description=f"Scraping data from {platform} with keyword '{keywords}' on {get_jakarta_time().strftime('%Y-%m-%d %H:%M')}",
            uploaded_by=current_user.id,
            status='Raw',
            total_records=0
        )
        db.session.add(new_dataset)
        db.session.flush()
        
        # Prepare date arguments if available
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        # Facebook specific parameters
        location_uid = data.get('location_uid')
        recent_posts = data.get('recent_posts', False)
        
        # Start Apify Job
        try:
            apify_run = ApifyService.start_scraping_job(
                platform=platform,
                keywords=keywords,
                max_results=int(max_results),
                start_date=start_date,
                end_date=end_date,
                location_uid=location_uid,
                recent_posts=recent_posts,
                language=language
            )
            apify_run_id = apify_run.get('id')
            apify_dataset_id = apify_run.get('defaultDatasetId')
            
            # Persist job details in Dataset model instead of in-memory
            new_dataset.external_id = apify_run_id
            new_dataset.meta_info = {
                'start_time': get_jakarta_time().isoformat(),
                'max_results': int(max_results),
                'platform': platform,
                'keywords': keywords,
                'apify_run_id': apify_run_id,
                'apify_dataset_id': apify_dataset_id,
                'language': language
            }
            db.session.commit()
            
            generate_activity_log(
                action='scraping',
                description=f'Started scraping {platform} for keyword: {keywords}',
                user_id=current_user.id,
                icon='fa-robot',
                color='warning'
            )
            
            return jsonify({
                'success': True, 
                'job_id': new_dataset.id, 
                'run_id': apify_run_id, 
                'apify_dataset_id': apify_dataset_id,
                'requires_mapping': True
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f"Failed to start scraping: {str(e)}"}), 500

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@scraper_bp.route('/process_scraping_column_mapping', methods=['POST'])
@login_required
def process_scraping_column_mapping():
    data = request.get_json() or {}
    dataset_id = data.get('dataset_id')
    apify_dataset_id = data.get('apify_dataset_id')
    
    content_col = data.get('content_column')
    username_col = data.get('username_column')
    url_col = data.get('url_column')
    
    if dataset_id:
        dataset = Dataset.query.get(dataset_id)
        if not dataset:
            return jsonify({'success': False, 'message': 'Dataset not found'}), 404
        if dataset.uploaded_by != current_user.id:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    else:
        # Fallback to latest
        dataset = Dataset.query.filter(Dataset.name.like('Scraping%'), Dataset.uploaded_by == current_user.id).order_by(Dataset.created_at.desc()).first()
        if not dataset:
            return jsonify({'success': False, 'message': 'Scraping dataset not found'}), 400
            
    if not apify_dataset_id:
        # Try to find from active jobs or dataset metadata
        if dataset and dataset.meta_info:
            apify_dataset_id = dataset.meta_info.get('apify_dataset_id')
        
        # Fallback to in-memory store if not found in metadata (backward compatibility)
        if not apify_dataset_id:
            store = current_app.config.get('SCRAPING_JOBS', {})
            for job in store.values():
                if job.get('dataset_id') == dataset.id:
                    apify_dataset_id = job.get('apify_dataset_id')
                    break
    
    if not apify_dataset_id:
         return jsonify({'success': False, 'message': 'Apify Dataset ID required'}), 400
         
    try:
        # Fetch all items from Apify
        items = ApifyService.get_dataset_items(apify_dataset_id)
        current_app.logger.info(f"Apify Dataset {apify_dataset_id} items count: {len(items)}")
        
        # If no items, try to fetch from run stats or check if run is still running/failed
        if not items:
             current_app.logger.warning(f"No items found for dataset {apify_dataset_id}")
             # Check run status if possible (optional, might need run_id)
             
        # Parse platform and keyword from dataset name (format: "Scraping {Platform} - {Keyword}")
        platform = 'unknown'
        keyword = 'unknown'
        if dataset.name.startswith('Scraping '):
            parts = dataset.name[9:].split(' - ', 1)
            if len(parts) >= 1:
                platform = parts[0].lower()
            if len(parts) >= 2:
                keyword = parts[1]
        
        count = 0
        for raw_item in items:
            # Flatten item first to handle nested objects in columns
            item = {}
            for k, v in raw_item.items():
                if isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        item[f"{k}_{sub_k}"] = sub_v
                    # Keep original for fallback logic
                    item[k] = v
                else:
                    item[k] = v
            
            # Map item keys to our model
            content = item.get(content_col, '')
            # Try to get content from original raw item if flattened key failed or empty
            if not content and content_col in raw_item:
                 content = raw_item[content_col]
                 
            # Skip empty content
            if not content:
                continue
                
            username = item.get(username_col, 'unknown')
            if username == 'unknown' and username_col in raw_item:
                username = raw_item[username_col]
                
            url = item.get(url_col, '')
            if not url and url_col in raw_item:
                url = raw_item[url_col]
            
            # Additional fields (best effort mapping for social media metrics)
            likes = item.get('likes') or item.get('favorite_count') or item.get('likeCount') or item.get('diggCount') or 0
            retweets = item.get('retweets') or item.get('retweet_count') or item.get('repostCount') or 0
            replies = item.get('replies') or item.get('reply_count') or item.get('commentCount') or 0
            shares = item.get('shares') or item.get('shareCount') or 0
            views = item.get('views') or item.get('view_count') or item.get('playCount') or 0
            
            # Ensure types
            try:
                likes = int(likes)
            except:
                likes = 0
                
            try:
                retweets = int(retweets)
            except:
                retweets = 0
                
            try:
                replies = int(replies)
            except:
                replies = 0
                
            try:
                shares = int(shares)
            except:
                shares = 0
                
            try:
                views = int(views)
            except:
                views = 0
                
            # Handle Twitter object structure (sometimes username is inside 'user' or 'author')
            if isinstance(username, dict):
                username = username.get('screen_name') or username.get('username') or username.get('name') or 'unknown'
            elif not username or username == 'unknown' or (isinstance(username, str) and username.isdigit()):
                # Try fallback fields for username
                # Twitter: user.screen_name, author.userName
                # TikTok: authorMeta.name, authorMeta.nickName, author.uniqueId
                username = (item.get('screen_name') or 
                           item.get('user', {}).get('screen_name') or 
                           item.get('user', {}).get('username') or 
                           item.get('core', {}).get('user_results', {}).get('result', {}).get('legacy', {}).get('screen_name') or # Deeply nested Twitter structure
                           item.get('author', {}).get('userName') or 
                           item.get('author', {}).get('uniqueId') or 
                           item.get('authorMeta', {}).get('name') or 
                           item.get('authorMeta', {}).get('nickName') or 
                           'unknown')
                
                # Special check for TikTok structure which is often nested or flattened
                if platform.lower() == 'tiktok':
                     # Prioritize uniqueId or name over numeric IDs
                     tiktok_user = (item.get('authorMeta', {}).get('name') or 
                                   item.get('authorMeta', {}).get('nickName') or 
                                   item.get('author_uniqueId') or 
                                   item.get('author_nickname') or 
                                   item.get('author_userName'))
                     
                     if tiktok_user and not str(tiktok_user).isdigit():
                         username = tiktok_user
                
                # Special check for Facebook structure
                if platform.lower() == 'facebook':
                    # Check for author_name in top level or inside user object
                    facebook_user = (item.get('author_name') or
                                    item.get('user', {}).get('name') or
                                    item.get('user', {}).get('username') or
                                    item.get('userName') or
                                    item.get('authorName') or # Common in some scrapers
                                    item.get('user_name') or
                                    item.get('name')) # Sometimes just name
                    
                    # If still not found, try to extract from URL if it's a profile URL
                    if not facebook_user and url:
                        # Try to extract from facebook.com/username/posts/...
                        fb_match = re.search(r'facebook\.com/([^/?#]+)', url)
                        if fb_match:
                            potential_user = fb_match.group(1)
                            # Avoid 'groups', 'pages', 'story' etc if possible, but better than nothing
                            if potential_user not in ['groups', 'watch', 'story', 'permalink']:
                                facebook_user = potential_user
                                
                    if facebook_user:
                        username = facebook_user
                
            # Handle Twitter content structure (sometimes content is 'full_text' or 'text')
            if not content:
                content = item.get('full_text') or item.get('text') or item.get('description') or ''
                
            # Handle URL structure
            if not url:
                url = (item.get('url') or 
                      item.get('expanded_url') or 
                      item.get('postUrl') or 
                      item.get('webUrl') or 
                      item.get('webVideoUrl') or 
                      '')
            
            # Extract username from URL if still unknown or looks like a URL (user mapped URL to username)
            if (not username or username == 'unknown' or username == 'None' or 'http' in str(username)) and url:
                # Pattern for Twitter: twitter.com/username/status/... or x.com/username/...
                twitter_match = re.search(r'https?://(?:www\.)?(?:twitter|x)\.com/([^/?#]+)', url)
                if twitter_match:
                    username = twitter_match.group(1)
                
                # Pattern for TikTok: tiktok.com/@username/...
                tiktok_match = re.search(r'https?://(?:www\.)?tiktok\.com/@([^/?#]+)', url)
                if tiktok_match:
                    username = tiktok_match.group(1)

            raw_data = RawDataScraper(
                username=str(username)[:255],
                content=str(content),
                url=str(url),
                platform=platform,
                keyword=keyword,
                scrape_date=get_jakarta_time().date(),
                status='raw',
                dataset_id=dataset.id,
                dataset_name=dataset.name,
                scraped_by=current_user.id,
                likes=likes,
                retweets=retweets,
                replies=replies,
                shares=shares,
                comments=replies,
                views=views
            )
            db.session.add(raw_data)
            count += 1
            
        dataset.total_records = count
        dataset.status = 'Raw'
        db.session.commit()
        
        generate_activity_log(
            action='scraping',
            description=f'Completed scraping data processing: {dataset.name} ({count} records)',
            user_id=current_user.id,
            icon='fa-save',
            color='success'
        )
        
        return jsonify({'success': True, 'dataset_id': dataset.id, 'total_records': count})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f"Error saving data: {str(e)}"}), 500
