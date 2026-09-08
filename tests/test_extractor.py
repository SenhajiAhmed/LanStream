"""
Unit test for Search and Extractor services
"""
import unittest
from services.search_service import SearchService
from services.extractor_service import ExtractorService


class TestExtractor(unittest.TestCase):
    def setUp(self):
        self.search_service = SearchService()
        self.extractor_service = ExtractorService()

    def test_search_and_extract(self):
        # 1. Search query
        try:
            videos = self.search_service.search("حرامية")
        except Exception as e:
            self.skipTest(f"Live network access unavailable: {e}")
        if not videos:
            self.skipTest("Live search returned no results (site might be blocking or offline)")

        # 2. Find Haramiya F KG2
        target_video = None
        for v in videos:
            if "كي جي" in v.title:
                target_video = v
                break

        self.assertIsNotNone(target_video, "Should find 'حرامية في كي جي تو'")
        print(f"\n[Test] Found video: {target_video.title} (ID: {target_video.id})")

        # 3. Extract stream URL
        stream_url = self.extractor_service.extract_stream(target_video)
        self.assertIsNotNone(stream_url, "Should extract a valid stream URL")
        self.assertTrue(stream_url.startswith("http"), "Stream URL should start with http")
        self.assertTrue(".m3u8" in stream_url, "Stream URL should be an HLS m3u8 playlist")
        print(f"[Test] Successfully extracted master stream: {stream_url[:100]}...\n")


if __name__ == "__main__":
    unittest.main()
