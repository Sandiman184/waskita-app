#!/usr/bin/env python3
"""
Script untuk memvalidasi dan memperbaiki masalah di VPS Waskita
"""

import os
import sys
import subprocess
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('vps_validation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_command(cmd, cwd=None):
    """Jalankan command dan return output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)

def check_docker_status():
    """Cek status Docker di VPS"""
    logger.info("Memeriksa status Docker...")
    
    # Cek Docker service
    code, out, err = run_command("sudo systemctl is-active docker")
    if code == 0 and "active" in out.lower():
        logger.info("✓ Docker service aktif")
    else:
        logger.error("✗ Docker service tidak aktif")
        logger.error(f"Error: {err}")
        return False
    
    # Cek Docker Compose
    code, out, err = run_command("docker-compose --version")
    if code == 0:
        logger.info(f"✓ Docker Compose terinstall: {out.strip()}")
    else:
        logger.error("✗ Docker Compose tidak terinstall")
        return False
    
    return True

def check_docker_containers():
    """Cek status container Docker"""
    logger.info("Memeriksa container Docker...")
    
    code, out, err = run_command("docker ps -a")
    if code != 0:
        logger.error("✗ Gagal memeriksa container Docker")
        return False
    
    containers = out.strip().split('\n')[1:]  # Skip header
    waskita_containers = [c for c in containers if 'waskita' in c.lower()]
    
    if waskita_containers:
        logger.info("✓ Container Waskita ditemukan:")
        for container in waskita_containers:
            logger.info(f"  {container}")
    else:
        logger.warning("⚠ Container Waskita tidak ditemukan")
    
    return True

def check_models_directory():
    """Cek direktori model"""
    logger.info("Memeriksa direktori model...")
    
    models_path = Path("models")
    if models_path.exists():
        logger.info("✓ Direktori models ditemukan")
        
        # Cek subdirectories
        embeddings_path = models_path / "embeddings"
        navesbayes_path = models_path / "navesbayes"
        
        if embeddings_path.exists():
            logger.info("✓ Direktori embeddings ditemukan")
            w2v_files = list(embeddings_path.glob("*.model"))
            if w2v_files:
                logger.info(f"✓ File Word2Vec ditemukan: {[f.name for f in w2v_files]}")
            else:
                logger.error("✗ File Word2Vec tidak ditemukan")
                return False
        else:
            logger.error("✗ Direktori embeddings tidak ditemukan")
            return False
            
        if navesbayes_path.exists():
            logger.info("✓ Direktori navesbayes ditemukan")
            nb_files = list(navesbayes_path.glob("*.pkl"))
            if len(nb_files) >= 3:
                logger.info(f"✓ File Naive Bayes ditemukan: {[f.name for f in nb_files]}")
            else:
                logger.error(f"✗ File Naive Bayes tidak lengkap. Ditemukan: {len(nb_files)}/3")
                return False
        else:
            logger.error("✗ Direktori navesbayes tidak ditemukan")
            return False
    else:
        logger.error("✗ Direktori models tidak ditemukan")
        return False
    
    return True

def check_environment():
    """Cek environment variables"""
    logger.info("Memeriksa environment variables...")
    
    required_vars = [
        'DISABLE_MODEL_LOADING',
        'WORD2VEC_MODEL_PATH', 
        'NAIVE_BAYES_MODEL1_PATH',
        'NAIVE_BAYES_MODEL2_PATH',
        'NAIVE_BAYES_MODEL3_PATH'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            logger.info(f"✓ {var}: {value}")
        else:
            logger.warning(f"⚠ {var}: tidak di-set")
            missing_vars.append(var)
    
    if missing_vars:
        logger.warning("Beberapa environment variables tidak di-set")
        return False
    
    return True

def check_ports():
    """Cek port yang digunakan"""
    logger.info("Memeriksa port...")
    
    ports_to_check = [80, 443, 5000]
    
    for port in ports_to_check:
        code, out, err = run_command(f"sudo netstat -tuln | grep :{port}")
        if code == 0 and out.strip():
            logger.info(f"✓ Port {port} digunakan: {out.strip()}")
        else:
            logger.warning(f"⚠ Port {port} tidak digunakan")
    
    return True

def fix_model_paths():
    """Perbaiki path model untuk VPS"""
    logger.info("Memperbaiki path model...")
    
    # Set environment variables untuk VPS
    model_vars = {
        'WORD2VEC_MODEL_PATH': '/app/models/embeddings/wiki_word2vec_csv_updated.model',
        'NAIVE_BAYES_MODEL1_PATH': '/app/models/navesbayes/naive_bayes_model1.pkl',
        'NAIVE_BAYES_MODEL2_PATH': '/app/models/navesbayes/naive_bayes_model2.pkl',
        'NAIVE_BAYES_MODEL3_PATH': '/app/models/navesbayes/naive_bayes_model3.pkl',
        'DISABLE_MODEL_LOADING': 'False'
    }
    
    for var, value in model_vars.items():
        os.environ[var] = value
        logger.info(f"✓ Set {var}={value}")
    
    return True

def test_model_loading():
    """Test loading model"""
    logger.info("Testing model loading...")
    
    try:
        # Import dependencies
        import sys
        sys.path.insert(0, '.')
        
        from app import load_models, app
        
        # Test model loading
        with app.app_context():
            load_models()
            
            # Check if models are loaded
            if hasattr(app.config, 'word2vec_model') and app.config.word2vec_model:
                logger.info("✓ Word2Vec model berhasil dimuat")
            else:
                logger.error("✗ Word2Vec model gagal dimuat")
                return False
                
            if hasattr(app.config, 'naive_bayes_models') and app.config.naive_bayes_models:
                logger.info(f"✓ {len(app.config.naive_bayes_models)} Naive Bayes models berhasil dimuat")
            else:
                logger.error("✗ Naive Bayes models gagal dimuat")
                return False
        
        logger.info("🎉 SEMUA MODEL BERHASIL DILOAD DI VPS!")
        return True
        
    except Exception as e:
        logger.error(f"✗ Error saat testing model loading: {e}")
        return False

def main():
    """Main function"""
    logger.info("=" * 60)
    logger.info("VALIDASI DAN PERBAIKAN VPS WASKITA")
    logger.info("=" * 60)
    
    # Cek environment
    checks = [
        ("Docker Status", check_docker_status),
        ("Docker Containers", check_docker_containers),
        ("Models Directory", check_models_directory),
        ("Environment Variables", check_environment),
        ("Port Usage", check_ports),
        ("Fix Model Paths", fix_model_paths),
        ("Model Loading Test", test_model_loading)
    ]
    
    results = []
    for check_name, check_func in checks:
        logger.info(f"\n{'='*20} {check_name} {'='*20}")
        try:
            success = check_func()
            results.append((check_name, success))
            if success:
                logger.info(f"✓ {check_name}: BERHASIL")
            else:
                logger.error(f"✗ {check_name}: GAGAL")
        except Exception as e:
            logger.error(f"✗ {check_name}: ERROR - {e}")
            results.append((check_name, False))
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("HASIL VALIDASI:")
    logger.info("="*60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for check_name, success in results:
        status = "✓ BERHASIL" if success else "✗ GAGAL"
        logger.info(f"{status}: {check_name}")
    
    logger.info(f"\nTOTAL: {passed}/{total} checks passed")
    
    if passed == total:
        logger.info("🎉 VPS SIAP DIGUNAKAN!")
        return True
    else:
        logger.warning("⚠ PERLU PERBAIKAN! Lihat log untuk detail.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)