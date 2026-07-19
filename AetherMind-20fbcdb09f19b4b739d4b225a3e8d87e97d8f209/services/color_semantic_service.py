import numpy as np
from PIL import Image
import io
from typing import List, Dict, Any, Optional
from models.document_model import ColorPaletteModel, ColorSemanticModel

class ColorSemanticService:
    def extract_palette(self, image_bytes: bytes, num_colors: int = 8) -> ColorPaletteModel:
        """
        Extracts dominant colors and semantic labels from an image.
        """
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img = img.convert("RGB")
            # Resize for faster processing
            img.thumbnail((200, 200))
            
            # Convert to numpy array
            data = np.array(img)
            pixels = data.reshape(-1, 3)
            
            # Basic clustering (K-Means simplified)
            from sklearn.cluster import KMeans
            kmeans = KMeans(n_clusters=num_colors, n_init=10, random_state=42)
            kmeans.fit(pixels)
            
            colors = kmeans.cluster_centers_.astype(int)
            hex_colors = [f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}".upper() for c in colors]
            
            return ColorPaletteModel(
                dominant_colors=hex_colors,
                semantic_labels=self.semantic_color_labels(hex_colors)
            )
        except Exception as e:
            print(f"[ColorSemanticService] Palette extraction failed: {e}")
            return ColorPaletteModel()

    def cluster_colors(self, hex_colors: List[str], tolerance: int = 30) -> Dict[str, List[str]]:
        """
        Clusters similar hex colors together.
        """
        clusters = {}
        for hex_c in hex_colors:
            r, g, b = self._hex_to_rgb(hex_c)
            found = False
            for key in clusters:
                kr, kg, kb = self._hex_to_rgb(key)
                dist = np.sqrt((r-kr)**2 + (g-kg)**2 + (b-kb)**2)
                if dist < tolerance:
                    clusters[key].append(hex_c)
                    found = True
                    break
            if not found:
                clusters[hex_c] = [hex_c]
        return clusters

    def legend_mapping(self, image_summary: str) -> Dict[str, str]:
        """
        Heuristic to extract hex-to-label mapping from LLM summary text.
        """
        import re
        # Look for patterns like "#0099A8: India Gen Zs" or "India Gen Zs (#0099A8)"
        mapping = {}
        # Pattern: #HEX: Label or Label (#HEX)
        matches = re.findall(r'(#[0-9A-Fa-f]{6})\s*[:\-]\s*([^,\n\.]+)', image_summary)
        for hex_c, label in matches:
            mapping[hex_c.upper()] = label.strip()
            
        reverse_matches = re.findall(r'([^,\n\.]+)\s*\((#[0-9A-Fa-f]{6})\)', image_summary)
        for label, hex_c in reverse_matches:
            mapping[hex_c.upper()] = label.strip()
            
        return mapping

    def semantic_color_labels(self, hex_colors: List[str]) -> List[ColorSemanticModel]:
        """
        Assigns basic semantic purposes to colors.
        """
        labels = []
        for hex_c in hex_colors:
            r, g, b = self._hex_to_rgb(hex_c)
            brightness = (r * 299 + g * 587 + b * 114) / 1000
            
            purpose = "series_mapping"
            if brightness > 240:
                purpose = "background"
            elif brightness < 30:
                purpose = "text"
            
            labels.append(ColorSemanticModel(
                label=self._get_color_name(hex_c),
                hex_color=hex_c,
                purpose=purpose
            ))
        return labels

    def _hex_to_rgb(self, hex_c: str):
        hex_c = hex_c.lstrip('#')
        return tuple(int(hex_c[i:i+2], 16) for i in (0, 2, 4))

    def _get_color_name(self, hex_c: str) -> str:
        # Simplified color naming
        r, g, b = self._hex_to_rgb(hex_c)
        if r > 200 and g < 100 and b < 100: return "Red"
        if g > 200 and r < 100 and b < 100: return "Green"
        if b > 200 and r < 100 and g < 100: return "Blue"
        if r > 200 and g > 200 and b < 100: return "Yellow"
        if r > 200 and b > 200 and g < 100: return "Magenta"
        if g > 200 and b > 200 and r < 100: return "Cyan"
        if r < 50 and g < 50 and b < 50: return "Black"
        if r > 200 and g > 200 and b > 200: return "White"
        return "Custom"
