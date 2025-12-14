from models.models import db, Dataset, RawData, RawDataScraper, CleanDataUpload, CleanDataScraper
from utils.utils import clean_text, check_cleaned_content_duplicate_by_dataset

def process_cleaning(dataset_id, user_id):
    """
    Process cleaning for a single dataset (synchronous)
    """
    dataset = Dataset.query.get(dataset_id)
    if not dataset:
        raise ValueError("Dataset not found")
        
    processed_count = 0
    
    # Process Upload Data
    raw_uploads = RawData.query.filter_by(dataset_id=dataset.id, status='raw').all()
    for raw_data in raw_uploads:
        try:
            cleaned_content = clean_text(raw_data.content)
            
            # Check for duplicate cleaned content in the same dataset
            if check_cleaned_content_duplicate_by_dataset(cleaned_content, dataset.id):
                raw_data.status = 'ignored' # Mark as ignored/duplicate
                continue

            clean_data = CleanDataUpload(
                raw_data_id=raw_data.id,
                username=raw_data.username,
                content=raw_data.content,
                cleaned_content=cleaned_content,
                url=raw_data.url,
                platform=raw_data.platform,
                dataset_id=raw_data.dataset_id,
                cleaned_by=user_id
            )
            db.session.add(clean_data)
            raw_data.status = 'cleaned'
            processed_count += 1
        except Exception as e:
            print(f"Error cleaning upload {raw_data.id}: {str(e)}")
            
    # Process Scraper Data
    raw_scrapers = RawDataScraper.query.filter_by(dataset_id=dataset.id, status='raw').all()
    for raw_scraper in raw_scrapers:
        try:
            cleaned_content = clean_text(raw_scraper.content)
            
            # Check for duplicate cleaned content in the same dataset
            if check_cleaned_content_duplicate_by_dataset(cleaned_content, dataset.id):
                raw_scraper.status = 'ignored' # Mark as ignored/duplicate
                continue

            clean_scraper_obj = CleanDataScraper(
                raw_data_scraper_id=raw_scraper.id,
                username=raw_scraper.username,
                content=raw_scraper.content,
                cleaned_content=cleaned_content,
                url=raw_scraper.url,
                platform=raw_scraper.platform,
                keyword=raw_scraper.keyword,
                dataset_id=raw_scraper.dataset_id,
                cleaned_by=user_id
            )
            db.session.add(clean_scraper_obj)
            raw_scraper.status = 'cleaned'
            processed_count += 1
        except Exception as e:
            print(f"Error cleaning scraper {raw_scraper.id}: {str(e)}")
            
    dataset.status = 'Cleaned'
    dataset.cleaned_records = processed_count
    db.session.commit()
    
    return processed_count

def process_bulk_cleaning(app, dataset_ids, task_id, user_id):
    with app.app_context():
        try:
            progress_dict = app.config['CLEANING_PROGRESS'][task_id]
            
            total_records = 0
            datasets = Dataset.query.filter(Dataset.id.in_(dataset_ids)).all()
            
            for dataset in datasets:
                raw_upload_count = RawData.query.filter_by(dataset_id=dataset.id, status='raw').count()
                raw_scraper_count = RawDataScraper.query.filter_by(dataset_id=dataset.id, status='raw').count()
                total_records += (raw_upload_count + raw_scraper_count)
            
            progress_dict['total'] = total_records
            progress_dict['status'] = 'processing'
            
            if total_records == 0:
                progress_dict['progress'] = 100
                progress_dict['status'] = 'completed'
                progress_dict['message'] = 'No raw data to clean'
                return

            processed_count = 0
            ignored_count = 0
            
            for dataset in datasets:
                current_dataset_processed_start = processed_count
                # Process Upload Data
                raw_uploads = RawData.query.filter_by(dataset_id=dataset.id, status='raw').all()
                for raw_data in raw_uploads:
                    try:
                        cleaned_content = clean_text(raw_data.content)
                        
                        # Check for duplicate cleaned content in the same dataset
                        if check_cleaned_content_duplicate_by_dataset(cleaned_content, dataset.id):
                             raw_data.status = 'ignored' # Mark as ignored/duplicate
                             # We still count it as processed, but maybe not add to clean data?
                             # Or we can skip adding to clean data
                             processed_count += 1
                             ignored_count += 1
                             progress_dict['current'] = processed_count
                             progress_dict['ignored_count'] = ignored_count
                             progress_dict['progress'] = int((processed_count / total_records) * 100)
                             continue

                        clean_data = CleanDataUpload(
                            raw_data_id=raw_data.id,
                            username=raw_data.username,
                            content=raw_data.content,
                            cleaned_content=cleaned_content,
                            url=raw_data.url,
                            platform=raw_data.platform,
                            dataset_id=raw_data.dataset_id,
                            cleaned_by=user_id
                        )
                        db.session.add(clean_data)
                        raw_data.status = 'cleaned'
                        
                        processed_count += 1
                        progress_dict['current'] = processed_count
                        progress_dict['progress'] = int((processed_count / total_records) * 100)
                        
                    except Exception as e:
                        progress_dict['errors'].append(f"Error cleaning upload {raw_data.id}: {str(e)}")
                
                db.session.commit()
                
                # Process Scraper Data
                raw_scrapers = RawDataScraper.query.filter_by(dataset_id=dataset.id, status='raw').all()
                for raw_scraper in raw_scrapers:
                    try:
                        cleaned_content = clean_text(raw_scraper.content)
                        
                        # Check for duplicate cleaned content in the same dataset
                        if check_cleaned_content_duplicate_by_dataset(cleaned_content, dataset.id):
                             raw_scraper.status = 'ignored'
                             processed_count += 1
                             ignored_count += 1
                             progress_dict['current'] = processed_count
                             progress_dict['ignored_count'] = ignored_count
                             progress_dict['progress'] = int((processed_count / total_records) * 100)
                             continue

                        clean_scraper_obj = CleanDataScraper(
                            raw_data_scraper_id=raw_scraper.id,
                            username=raw_scraper.username,
                            content=raw_scraper.content,
                            cleaned_content=cleaned_content,
                            url=raw_scraper.url,
                            platform=raw_scraper.platform,
                            keyword=raw_scraper.keyword,
                            dataset_id=raw_scraper.dataset_id,
                            cleaned_by=user_id
                        )
                        db.session.add(clean_scraper_obj)
                        raw_scraper.status = 'cleaned'
                        
                        processed_count += 1
                        progress_dict['current'] = processed_count
                        progress_dict['progress'] = int((processed_count / total_records) * 100)
                        
                    except Exception as e:
                        progress_dict['errors'].append(f"Error cleaning scraper {raw_scraper.id}: {str(e)}")
                
                dataset.status = 'Cleaned'
                dataset.cleaned_records = (dataset.cleaned_records or 0) + (processed_count - current_dataset_processed_start)
                db.session.commit()
            
            progress_dict['status'] = 'completed'
            progress_dict['message'] = f'Successfully cleaned {processed_count - ignored_count} data. {ignored_count} data ignored as duplicates.'
            
        except Exception as e:
            app.logger.error(f"Bulk cleaning error: {str(e)}")
            progress_dict['status'] = 'error'
            progress_dict['message'] = str(e)
