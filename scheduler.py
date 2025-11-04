import schedule
import time
import threading
import logging
from datetime import datetime
from flask import current_app
from models import db, RawDataScraper, CleanDataScraper, ClassificationResult
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
                    logger.info("Tidak ada data scraper orphan yang ditemukan")
                    return 0
                
                orphaned_count = len(orphaned_raw_data)
                orphaned_ids = [data.id for data in orphaned_raw_data]
                
                logger.info(f"Ditemukan {orphaned_count} data scraper orphan")
                
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
                    logger.info(f"Menghapus {len(clean_scraper_ids)} hasil klasifikasi terkait")
                
                # Hapus clean_data_scraper yang terkait dengan raw_data_scraper orphan
                if clean_scraper_ids:
                    db.session.query(CleanDataScraper).filter(
                        CleanDataScraper.raw_data_scraper_id.in_(orphaned_ids)
                    ).delete(synchronize_session=False)
                    logger.info(f"Menghapus {len(clean_scraper_ids)} data scraper bersih terkait")
                
                # Hapus raw_data_scraper orphan
                db.session.query(RawDataScraper).filter(
                    RawDataScraper.id.in_(orphaned_ids)
                ).delete(synchronize_session=False)
                
                db.session.commit()
                logger.info(f"Berhasil menghapus {orphaned_count} data scraper orphan")
                
                return orphaned_count
                
        except Exception as e:
            logger.error(f"Error saat membersihkan data scraper orphan: {str(e)}")
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
                
                # Update statistics using the same method as routes.py
                stats.total_raw_upload = db.session.execute(text("SELECT COUNT(*) FROM raw_data")).scalar() or 0
                stats.total_raw_scraper = db.session.execute(text("SELECT COUNT(*) FROM raw_data_scraper")).scalar() or 0
                stats.total_clean_upload = db.session.execute(text("SELECT COUNT(*) FROM clean_data_upload")).scalar() or 0
                stats.total_clean_scraper = db.session.execute(text("SELECT COUNT(*) FROM clean_data_scraper")).scalar() or 0
                stats.total_classified = db.session.execute(text("SELECT COUNT(*) FROM classification_results")).scalar() or 0
                stats.total_radikal = db.session.execute(text("SELECT COUNT(*) FROM classification_results WHERE prediction = 'radikal'")).scalar() or 0
                stats.total_non_radikal = db.session.execute(text("SELECT COUNT(*) FROM classification_results WHERE prediction = 'non-radikal'")).scalar() or 0
                
                # Calculate percentages
                if stats.total_classified > 0:
                    stats.radikal_percentage = (stats.total_radikal / stats.total_classified) * 100
                    stats.non_radikal_percentage = (stats.total_non_radikal / stats.total_classified) * 100
                else:
                    stats.radikal_percentage = 0
                    stats.non_radikal_percentage = 0
                
                db.session.commit()
                logger.info("Statistik dashboard berhasil diperbarui")
                
        except Exception as e:
            logger.error(f"Error saat memperbarui statistik: {str(e)}")
            db.session.rollback()
    
    def scheduled_cleanup(self):
        """Fungsi yang akan dijalankan secara terjadwal"""
        logger.info(f"Memulai pembersihan otomatis data scraper orphan - {datetime.now()}")
        
        deleted_count = self.cleanup_orphaned_scraper_data()
        
        if deleted_count > 0:
            self.update_statistics()
            logger.info(f"Pembersihan selesai: {deleted_count} data scraper orphan dihapus")
        else:
            logger.info("Pembersihan selesai: tidak ada data orphan yang dihapus")
    
    def start_scheduler(self):
        """Memulai scheduler untuk pembersihan otomatis"""
        if self.running:
            logger.warning("Scheduler sudah berjalan")
            return
            
        # Jadwalkan pembersihan setiap hari pada pukul 02:00
        schedule.every().day.at("02:00").do(self.scheduled_cleanup)
        
        # Jadwalkan pembersihan setiap 6 jam untuk pembersihan lebih sering
        schedule.every(6).hours.do(self.scheduled_cleanup)
        
        self.running = True
        
        def run_scheduler():
            logger.info("Scheduler pembersihan data scraper orphan dimulai")
            while self.running:
                schedule.run_pending()
                time.sleep(60)  # Check setiap menit
                
        self.scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("Scheduler berhasil dimulai - pembersihan otomatis setiap 6 jam dan setiap hari pukul 02:00")
    
    def stop_scheduler(self):
        """Menghentikan scheduler"""
        if not self.running:
            logger.warning("Scheduler tidak sedang berjalan")
            return
            
        self.running = False
        schedule.clear()
        
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
            
        logger.info("Scheduler pembersihan data scraper orphan dihentikan")
    
    def run_cleanup_now(self):
        """Menjalankan pembersihan secara manual"""
        logger.info("Menjalankan pembersihan manual data scraper orphan")
        deleted_count = self.cleanup_orphaned_scraper_data()
        
        if deleted_count > 0:
            self.update_statistics()
            
        return deleted_count

# Instance global scheduler
cleanup_scheduler = DataCleanupScheduler()