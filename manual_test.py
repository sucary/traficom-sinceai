import sys
from pathlib import Path

# Lisätään backend/src Pythonin polkuihin, jotta 'app' löytyy
sys.path.append(str(Path(__file__).parent / "backend" / "src"))

from app.rag.service import RAGService

if __name__ == "__main__":
    print("Aloitetaan RAG-palvelun testaus...")
    rag = RAGService()

    print("Rakennetaan/ladataan indeksiä (tämä voi kestää hetken ensimmäisellä kerralla)...")
    rag.ensure_index_built()

    print("Tehdään testikysely OpenCodelle...")
    vastaus = rag.query_rules(10700.0, "FIXED-SATELLITE")

    print("\n--- OPENCODEN VASTAUS ---")
    print(vastaus)
    print("-------------------------")