from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from pathlib import Path
from uuid import uuid4
import os
import boto3
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

load_dotenv()

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)

BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

def format_value(value):
    if value is None:
        return "Not provided"

    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" for k, v in value.items() if v not in (None, "", [], {}))

    if isinstance(value, list):
        return "; ".join(str(item) for item in value if item not in (None, "", [], {}))

    return str(value)

def write_procurement_pdf(document: dict) -> dict:
    output_dir = Path("generated_documents")
    output_dir.mkdir(parents=True, exist_ok=True)

    file_path = output_dir / f"{document['unique_id']}.pdf"

    pdf = canvas.Canvas(str(file_path), pagesize=A4)
    width, height = A4
    y = height - 50

    def line(label, value=""):
        nonlocal y
        pdf.drawString(50, y, f"{label}: {value}")
        y -= 22

    line("Procurement Document", document.get("unique_id"))
    line("Status", document.get("status"))
    line("Item", document.get("item_name"))
    line("Category", document.get("category"))
    line("Quantity", document.get("quantity"))
    line("Budget Per Item", document.get("budget_per_item"))
    line("Total Budget", document.get("total_budget"))
    line("Selected Product", format_value(document.get("selected_option")))
    line("Product Specifications", format_value(document.get("mandatory_specifications")))
    line("Vendor Recommendations", format_value(document.get("vendor_recommendations")))
    line("Delivery", format_value(document.get("delivery")))
    line("Approval Requirements", format_value(document.get("approval_requirements")))
    line("Procurement Method", document.get("procurement_method"))
    line("Final Summary", document.get("final_confirmed_summary"))

    pdf.showPage()
    pdf.save()
    s3_key = f"reports/{uuid4()}_{file_path.name}"
    s3.upload_file(
        str(file_path),
        BUCKET_NAME,
        s3_key,
        ExtraArgs={
            "ContentType": "application/pdf"
        }
    )
    download_url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": BUCKET_NAME,
            "Key": s3_key,
        },
        ExpiresIn=3600,
    )
    print("DEBUG s3_key:", s3_key)
    print("DEBUG download_url:", download_url)
    result = {
        "status": "created",
        "document_path": str(file_path),
        "document_id": document["unique_id"],
        "s3_key": s3_key,
        "download_url": download_url,
    }
    print("DEBUG final pdf result:", result)
    return result