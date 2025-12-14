import schedule
import time
import threading
import logging
from datetime import datetime, timedelta
from flask import current_app
from models.models import db, RawDataScraper, CleanDataScraper, ClassificationResult
from models.models_otp import RegistrationRequest, OTPEmailLog
from sqlalchemy import text

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataCleanupScheduler:
    def __init__(self, app=None):
        self.app = app
        self.scheduler_thread = None
        self.running = False
        
    def init_app(self, app):
        self.app = app
        
    def cleanup_orphaned_scraper_data(self):
        """Membersihkan data scraper yang tidak terkait dengan dataset (orphaned data)"""
        try:
            with self.app.app_context():
                # Cari raw_data_scraper yang tidak memiliki dataset_id (NULL)
                orphaned_raw_data = db.session.query(RawDataScraper).filter(
                    RawDataScraper.dataset_id.is_(None)
                ).all()
                
                if not orphaned_raw_data:
                    logger.info("No orphaned scraper data found")
                    return 0
                
                orphaned_count = len(orphaned_raw_data)
                orphaned_ids = [data.id for data in orphaned_raw_data]
                
                logger.info(f"Found {orphaned_count} orphaned scraper data items")
                
                # Ambil clean_scraper_ids yang terkait dengan raw_data_scraper orphan
                clean_scraper_data = db.session.query(CleanDataScraper).filter(
                    CleanDataScraper.raw_data_scraper_id.in_(orphaned_ids)
                ).all()
                
                clean_scraper_ids = [data.id for data in clean_scraper_data]
                
                # Hapus classification_results yang terkait dengan clean_data_scraper orphan
                if clean_scraper_ids:
                    db.session.query(ClassificationResult).filter(
                        ClassificationResult.data_type == 'scraper',
                        ClassificationResult.data_id.in_(clean_scraper_ids)
                    ).delete(synchronize_session=False)
                    logger.info(f"Deleting {len(clean_scraper_ids)} related classification results")
                
                # Hapus clean_data_scraper yang terkait dengan raw_data_scraper orphan
                if clean_scraper_ids:
                    db.session.query(CleanDataScraper).filter(
                        CleanDataScraper.raw_data_scraper_id.in_(orphaned_ids)
                    ).delete(synchronize_session=False)
                    logger.info(f"Deleting {len(clean_scraper_ids)} related clean scraper data items")
                
                # Hapus raw_data_scraper orphan
                db.session.query(RawDataScraper).filter(
                    RawDataScraper.id.in_(orphaned_ids)
                ).delete(synchronize_session=False)
                
                db.session.commit()
                logger.info(f"Successfully deleted {orphaned_count} orphaned scraper data items")
                
                return orphaned_count
                
        except Exception as e:
            logger.error(f"Error cleaning orphaned scraper data: {str(e)}")
            db.session.rollback()
            return 0
    
    def cleanup_expired_otp_data(self):
        """Membersihkan data OTP yang sudah expired dan data log email yang sudah lama"""
        try:
            with self.app.app_context():
                # Hapus registration requests yang sudah expired
                expired_otp_count = db.session.query(RegistrationRequest).filter(
                    RegistrationRequest.otp_expires_at < datetime.utcnow(),
                    RegistrationRequest.status == 'pending'
                ).delete(synchronize_session=False)
                
                # Hapus email logs yang lebih dari 30 hari
                thirty_days_ago = datetime.utcnow() - timedelta(days=30)
                old_email_logs_count = db.session.query(OTPEmailLog).filter(
                    OTPEmailLog.created_at < thirty_days_ago
                ).delete(synchronize_session=False)
                
                db.session.commit()
                
                logger.info(f"Successfully deleted {expired_otp_count} expired OTPs and {old_email_logs_count} old email logs")
                return expired_otp_count + old_email_logs_count
                
        except Exception as e:
            logger.error(f"Error cleaning expired OTP data: {str(e)}")
            db.session.rollback()
            return 0
    
    def update_statistics(self):
        """Update statistik dashboard setelah cleanup"""
        try:
            with self.app.app_context():
                from models import DatasetStatistics
                from sqlalchemy import text
                
                # Get or create statistics record
                stats = DatasetStatistics.query.first()
                if not stats:
                    stats = DatasetStatistics()
                    db.session.add(stats)
                
                # Update statistics - only count data that belongs to existing datasets
                stats.total_raw_upload = db.session.execute(text("SELECT COUNT(*) FROM raw_data WHERE dataset_id IS NOT NULL")).scalar() or 0
                stats.total_raw_scraper = db.session.execute(text("SELECT COUNT(*) FROM raw_data_scraper WHERE dataset_id IS NOT NULL")).scalar() or 0
                stats.total_clean_upload = db.session.execute(text("SELECT COUNT(*) FROM clean_data_upload WHERE dataset_id IS NOT NULL")).scalar() or 0
                stats.total_clean_scraper = db.session.execute(text("SELECT COUNT(*) FROM clean_data_scraper WHERE raw_data_scraper_id IN (SELECT id FROM raw_data_scraper WHERE dataset_id IS NOT NULL)")).scalar() or 0
                stats.total_classified = db.session.execute(text("""SELECT COUNT(*) FROM classification_results 
                WHERE (data_type = 'upload' AND data_id IN (SELECT id FROM clean_data_upload WHERE dataset_id IS NOT NULL))
                OR (data_type = 'scraper' AND data_id IN (SELECT id FROM clean_data_scraper WHERE raw_data_scraper_id IN (SELECT id FROM raw_data_scraper WHERE dataset_id IS NOT NULL)))""")).scalar() or 0
                stats.total_radikal = db.session.execute(text("""SELECT COUNT(*) FROM classification_results 
                WHERE prediction = 'radikal'
                AND ((data_type = 'upload' AND data_id IN (SELECT id FROM clean_data_upload WHERE dataset_id IS NOT NULL))
                OR (data_type = 'scraper' AND data_id IN (SELECT id FROM clean_data_scraper WHERE raw_data_scraper_id IN (SELECT id FROM raw_data_scraper WHERE dataset_id IS NOT NULL))))""")).scalar() or 0
                stats.total_non_radikal = db.session.execute(text("""SELECT COUNT(*) FROM classification_results 
                WHERE prediction = 'non-radikal'
                AND ((data_type = 'upload' AND data_id IN (SELECT id FROM clean_data_upload WHERE dataset_id IS NOT NULL))
                OR (data_type = 'scraper' AND data_id IN (SELECT id FROM clean_data_scraper WHERE raw_data_scraper_id IN (SELECT id FROM raw_data_scraper WHERE dataset_id IS NOT NULL))))""")).scalar() or 0
                
                # Calculate percentages
                if stats.total_classified > 0:
                    stats.radikal_percentage = (stats.total_radikal / stats.total_classified) * 100
                    stats.non_radikal_percentage = (stats.total_non_radikal / stats.total_classified) * 100
                else:
                    stats.radikal_percentage = 0
                    stats.non_radikal_percentage = 0
                
                db.session.commit()
                logger.info("Dashboard statistics successfully updated")
                
        except Exception as e:
            logger.error(f"Error updating statistics: {str(e)}")
            db.session.rollback()
    
    def scheduled_cleanup(self):
        """Fungsi yang akan dijalankan secara terjadwal"""
        logger.info(f"Starting automatic data cleanup - {datetime.now()}")
        
        # Cleanup data scraper orphan
        scraper_deleted_count = self.cleanup_orphaned_scraper_data()
        
        # Cleanup OTP expired data
        otp_deleted_count = self.cleanup_expired_otp_data()
        
        total_deleted = scraper_deleted_count + otp_deleted_count
        
        if total_deleted > 0:
            self.update_statistics()
            logger.info(f"Cleanup completed: {scraper_deleted_count} orphaned scraper data and {otp_deleted_count} expired OTP data deleted")
        else:
            logger.info("Cleanup completed: no data deleted")
    
    def start_scheduler(self):
        """Memulai scheduler untuk pembersihan otomatis"""
        if self.running:
            logger.warning("Scheduler is already running")
            return
            
        # Jadwalkan pembersihan setiap hari pada pukul 02:00
        schedule.every().day.at("02:00").do(self.scheduled_cleanup)
        
        # Jadwalkan pembersihan setiap 6 jam untuk pembersihan lebih sering
        schedule.every(6).hours.do(self.scheduled_cleanup)
        
        self.running = True
        
        def run_scheduler():
            logger.info("Orphaned scraper data cleanup scheduler started")
            while self.running:
                schedule.run_pending()
                time.sleep(60)  # Check setiap menit
                
        self.scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("Scheduler successfully started - automatic cleanup every 6 hours and daily at 02:00")
    
    def stop_scheduler(self):
        """Menghentikan scheduler"""
        if not self.running:
            logger.warning("Scheduler is not running")
            return
            
        self.running = False
        schedule.clear()
        
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
            
        logger.info("Orphaned scraper data cleanup scheduler stopped")
    
    def run_cleanup_now(self):
        """Menjalankan pembersihan secara manual"""
        logger.info("Running manual orphaned scraper data cleanup")
        deleted_count = self.cleanup_orphaned_scraper_data()
        
        if deleted_count > 0:
            self.update_statistics()
            
        return deleted_count

# Instance global scheduler
cleanup_scheduler = DataCleanupScheduler()
