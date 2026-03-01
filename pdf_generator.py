import os
from fpdf import FPDF
import logging

logger = logging.getLogger(__name__)

class PDF(FPDF):
    def header(self):
        # We can add custom header here if needed
        pass

    def footer(self):
        self.set_y(-15)
        # Arial italic 8
        self.set_font('helvetica', 'I', 8)
        # Page number
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='C')

def create_ats_cv_pdf(cv_text: str, output_path: str) -> bool:
    """
    Generates an ATS-friendly PDF from the provided CV text.
    The CV text should ideally be pre-formatted by the AI.
    """
    try:
        pdf = PDF()
        pdf.add_page()
        
        # Add a Unicode font (DejaVu) to support more characters.
        # Ensure the font file exists or fallback to Helvetica
        # We will use Helvetica for now as standard ATS-friendly font.
        pdf.set_font("Helvetica", size=11)
        
        # Add the text. Multi_cell handles line breaks.
        # utf-8 encoding is essential for any special characters
        pdf.multi_cell(0, 7, cv_text.encode('latin-1', 'replace').decode('latin-1'))
        
        pdf.output(output_path)
        logger.info(f"Successfully generated ATS PDF to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to generate ATS PDF: {e}")
        return False
