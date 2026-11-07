import os
import re
import numpy as np  # <--- TÄMÄ ON TÄRKEÄ

import faiss
import requests
from dotenv import load_dotenv

from app.config import PROJECT_ROOT
from app.rag.utils import processing
from app.rag.utils.retrieval import retrieve_relevant_chunks


class RAGService:
    def __init__(self):
        load_dotenv(PROJECT_ROOT / ".env")
        self.pdf_directory = PROJECT_ROOT / "data"
        self.index_path = self.pdf_directory / "faiss_index.idx"
        self.chunks_path = self.pdf_directory / "text_chunks.npy"
        self.api_url = os.getenv("OPENCODE_API_URL")
        self.api_key = os.getenv("OPENCODE_API_KEY")
        self.model = os.getenv("OPENCODE_MODEL", "opencode/big-pickle")

        if not self.api_url or not self.api_key:
            raise ValueError("OPENCODE_API_URL and OPENCODE_API_KEY must be configured")

        self.embedder = processing.get_embedder()
        self.ensure_index_built()

    def ensure_index_built(self):
        if self.index_path.is_file() and self.chunks_path.is_file():
            existing_index = faiss.read_index(os.fspath(self.index_path))
            if (
                existing_index.d == self.embedder.get_embedding_dimension()
                and existing_index.metric_type == faiss.METRIC_L2
            ):
                return

        if not self.pdf_directory.is_dir():
            raise FileNotFoundError(f"PDF directory does not exist: {self.pdf_directory}")

        texts = processing.extract_text_from_pdfs(self.pdf_directory)
        chunks = processing.chunk_text(texts)
        processing.create_faiss_index(
            chunks,
            index_path=self.index_path,
            chunks_path=self.chunks_path,
            embedder=self.embedder,
        )

    def query_rules(self, frequency_mhz: float, service_type: str) -> str:
        freq_ghz = frequency_mhz / 1000.0
        search_query = f"Frequency: {frequency_mhz} MHz or {freq_ghz} GHz; service type: {service_type}"
        
        # 1. Vektorihaku (hakee 10 pätkää)
        chunks = retrieve_relevant_chunks(
            search_query,
            self.embedder,
            k=10,
            index_path=self.index_path,
            chunks_path=self.chunks_path,
        )
        
        # 2. Pakotettu tekstihaku numerolle (koska vektorihaku epäonnistuu numeroissa)
        all_chunks = np.load(self.chunks_path, allow_pickle=True)
        freq_str1 = str(int(frequency_mhz))
        freq_str2 = str(freq_ghz)
        
        keyword_matches = []
        for chunk in all_chunks:
            if freq_str1 in chunk or freq_str2 in chunk or freq_str1.replace("0", " 0") in chunk:
                keyword_matches.append(chunk)
                if len(keyword_matches) >= 3:
                    break
                    
        # Yhdistetään tulokset ja poistetaan duplikaatit
        combined_chunks = list(dict.fromkeys(keyword_matches + chunks))
        context = "\n\n".join(combined_chunks)
        
        # DEBUG Tulostus, jotta näet mitä tapahtuu
        print(f"\n--- HAKUTULOS ---")
        print(f"Tekstihaku löysi {len(keyword_matches)} pätkää hakusanoilla '{freq_str1}' tai '{freq_str2}'.")
        print(f"Kontekstin kokonaispituus: {len(context)} merkkiä.")
        if len(keyword_matches) == 0:
            print(f"⚠️ VAROITUS: Taajuutta ei löytynyt tekstistä. PDF:n luku on epäonnistunut tai taajuus ei ole tiedostoissa.")
        print("-----------------\n")

        prompt = (
            "You are a Traficom spectrum regulation expert. Answer the question using "
            "the provided context. If the context does not contain enough information, "
            "state that clearly and do not invent regulatory requirements.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: Which rules apply to the {service_type} service at "
            f"{frequency_mhz} MHz? Explain the relevant requirements."
        )

        response = requests.post(
            self.api_url,
            headers={"Authorization": f"Bearer {self.api_key}",
                     "x-opencode-session": "test-session"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()