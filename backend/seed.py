"""
Seed the database with sample company data so the site is browsable out of
the box. Run with:  python seed.py
Re-running clears and reseeds the demo data (safe for dev; do NOT run
against a production DB with real stock already in it).

NOTE: image_url values here are placeholder stock-photo URLs (picsum.photos)
standing in for real product photography. Replace them with real slab photos
(ideally hosted in Supabase Storage) before going live — see Section 10.2
of the project report bundled with this codebase.
"""
from datetime import datetime, timedelta

from app import create_app
from models import db, Slab, Announcement, CustomerQuery
from utils.calc import calculate_slab_area

GODOWNS = [
    ("godown_1", "Bangalore Yard"),
    ("godown_2", "Chittoor Factory"),
    ("godown_3", "Vishakapatnam Export"),
]

FINISHES = ["Polished", "Honed", "Leathered", "Flamed", "Lappato"]

SAMPLE_SLABS = [
    dict(title="Black Galaxy Granite", category="Granite", godown=0, length=9, width=6, unit="feet",
         pieces=4, thickness=18, finish="Polished", rate=185, img=101, lot="BG-2026-A"),
    dict(title="Alaska White Granite", category="Granite", godown=0, length=8.5, width=5.5, unit="feet",
         pieces=3, thickness=18, finish="Polished", rate=165, img=102, lot="AW-2026-B"),
    dict(title="Tan Brown Granite", category="Granite", godown=1, length=9, width=6, unit="feet",
         pieces=6, thickness=20, finish="Flamed", rate=140, img=103, lot="TB-2026-C"),
    dict(title="Kashmir White Granite", category="Granite", godown=1, length=8, width=5, unit="feet",
         pieces=5, thickness=18, finish="Polished", rate=175, img=104, lot="KW-2026-D"),
    dict(title="Steel Grey Granite", category="Granite", godown=2, length=9, width=6, unit="feet",
         pieces=8, thickness=20, finish="Honed", rate=120, img=105, lot="SG-2026-E"),
    dict(title="Statuario Italian Marble", category="Italian Marble", godown=0, length=10, width=6, unit="feet",
         pieces=2, thickness=20, finish="Polished", rate=420, img=106, lot="ST-2026-F"),
    dict(title="Carrara White Marble", category="Italian Marble", godown=0, length=9, width=5.5, unit="feet",
         pieces=3, thickness=18, finish="Polished", rate=380, img=107, lot="CW-2026-G"),
    dict(title="Calacatta Gold Marble", category="Italian Marble", godown=1, length=10, width=6, unit="feet",
         pieces=2, thickness=20, finish="Polished", rate=560, img=108, lot="CG-2026-H"),
    dict(title="Makrana White Marble", category="Indian Marble", godown=1, length=8, width=5, unit="feet",
         pieces=6, thickness=18, finish="Polished", rate=95, img=109, lot="MW-2026-I"),
    dict(title="Rajnagar White Marble", category="Indian Marble", godown=2, length=8, width=5, unit="feet",
         pieces=7, thickness=18, finish="Honed", rate=85, img=110, lot="RW-2026-J"),
    dict(title="Absolute Black Quartz", category="Quartz", godown=2, length=9.5, width=6.5, unit="feet",
         pieces=4, thickness=20, finish="Polished", rate=210, img=111, lot="AQ-2026-K"),
    dict(title="Calacatta Quartz Slab", category="Quartz", godown=0, length=9.5, width=6.5, unit="feet",
         pieces=3, thickness=20, finish="Polished", rate=260, img=112, lot="CQ-2026-L"),
    dict(title="Amber Onyx", category="Onyx", godown=1, length=7, width=4.5, unit="feet",
         pieces=2, thickness=20, finish="Polished", rate=650, img=113, lot="AO-2026-M"),
    dict(title="White Onyx Backlit Panel", category="Onyx", godown=1, length=7, width=4, unit="feet",
         pieces=2, thickness=20, finish="Lappato", rate=720, img=114, lot="WO-2026-N"),
    dict(title="Autumn Brown Sandstone", category="Sandstone", godown=2, length=6, width=3, unit="feet",
         pieces=12, thickness=25, finish="Flamed", rate=45, img=115, lot="AS-2026-O"),
    dict(title="Mint Fossil Sandstone", category="Sandstone", godown=2, length=6, width=3, unit="feet",
         pieces=10, thickness=25, finish="Leathered", rate=52, img=116, lot="MF-2026-P"),
]

ANNOUNCEMENTS = [
    dict(title="Fresh Container Arrival", message="New Calacatta Gold & Statuario blocks just landed at the Bangalore Yard — first pick before they're gated for export orders.", type="arrival"),
    dict(title="Monsoon Clearance on Sandstone", message="Flat 10% off all Sandstone finishes across every yard, this month only.", type="offer"),
    dict(title="Export Counter Now Open", message="Suguna Export, Vishakapatnam is now taking bulk export enquiries directly — ask for the Vizag yard.", type="general"),
]


def run():
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        for s in SAMPLE_SLABS:
            godown_id, godown_name = GODOWNS[s["godown"]]
            area = calculate_slab_area(s["length"], s["width"], s["unit"], s["pieces"])
            slab = Slab(
                godown_id=godown_id,
                godown_name=godown_name,
                block_number=s["lot"],
                title=s["title"],
                category=s["category"],
                image_url=f"https://picsum.photos/seed/{s['img']}/900/700",
                length=s["length"],
                width=s["width"],
                unit=s["unit"],
                pieces=s["pieces"],
                total_sq_ft=area["totalSqFt"],
                total_sq_meters=area["totalSqMeters"],
                thickness_mm=s["thickness"],
                finish=s["finish"],
                price_per_sq_ft=s["rate"],
                is_sold=False,
                lot_name=s["lot"],
                created_at=datetime.utcnow(),
            )
            db.session.add(slab)

        today = datetime.utcnow().strftime("%Y-%m-%d")
        for a in ANNOUNCEMENTS:
            db.session.add(Announcement(
                title=a["title"], message=a["message"], type=a["type"],
                is_active=True, date=today,
            ))

        db.session.add(CustomerQuery(
            order_number="SBG-DEMO-0001",
            client_name="Ravi Kumar",
            mobile_number="+91 90000 00000",
            delivery_address="Whitefield, Bangalore",
            preferred_godown="godown_1",
            requirement="Need Black Galaxy Granite for kitchen countertop, approx 40 sq.ft.",
            dimension_unit="feet",
            requested_quantity_sqft=40,
            selected_slabs=[],
            total_estimated_cost=7400,
            status="Pending",
            created_at=datetime.utcnow() - timedelta(days=1),
        ))

        db.session.commit()
        print(f"Seeded {len(SAMPLE_SLABS)} slabs, {len(ANNOUNCEMENTS)} announcements, 1 sample query.")


if __name__ == "__main__":
    run()
