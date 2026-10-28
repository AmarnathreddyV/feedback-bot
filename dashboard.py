import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from common import get_reviews, update_review_status, create_demo_reviews

load_dotenv()
st.set_page_config(page_title="Niloufer Customer Experience", page_icon="☕", layout="wide")

st.markdown("""
<style>
:root { --coffee:#4a2c22; --cream:#fbf4e8; --gold:#c99a3d; }
.stApp { background: #fbf7f0; }
[data-testid="stSidebar"] { background: #efe2ce; }
h1, h2, h3 { color: #4a2c22; }
div[data-testid="stMetric"] { background: #fffaf2; border: 1px solid #ead9bd; padding: 14px; border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

st.title("☕ Niloufer Customer Experience Intelligence")
st.caption("WhatsApp feedback • AI sentiment analysis • Complaint tracking")
with st.sidebar:
    st.header("Niloufer Café")
    page = st.radio("Navigation", ["Dashboard", "All Reviews", "Complaints", "Reports", "Setup"])
    st.divider()
    st.caption("Starter build — add staff authentication before public deployment.")

if page == "Setup":
    st.subheader("Setup & connection status")
    supabase_ready = bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    openai_ready = bool(os.getenv("OPENAI_API_KEY"))
    whatsapp_ready = bool(os.getenv("WHATSAPP_ACCESS_TOKEN") and os.getenv("WHATSAPP_PHONE_NUMBER_ID"))
    st.write("Supabase database:", "Connected by configuration" if supabase_ready else "Local SQLite fallback")
    st.write("AI provider:", "OpenAI configured" if openai_ready else "Rule-based fallback (no AI API key)")
    st.write("WhatsApp Cloud API:", "Credentials configured" if whatsapp_ready else "Not configured / dry-run mode")
    st.info("To create illustrative data for a dashboard demo, click below. Demo reviews are clearly marked as portal_demo.")
    if st.button("Add demo reviews"):
        count = create_demo_reviews()
        st.success(f"Added {count} demo reviews." if count else "Reviews already exist; no demo data added.")
    st.markdown("Webhook endpoint: `/webhook/whatsapp`")
    st.markdown("QR image endpoint: `/qr` (requires WHATSAPP_PUBLIC_NUMBER)")
else:
    reviews = get_reviews()
    df = pd.DataFrame(reviews)
    if df.empty:
        st.info("No reviews yet. Use Setup → Add demo reviews to preview the portal, or connect WhatsApp to receive real feedback.")
    else:
        if "created_at" in df:
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
        if page == "Dashboard":
            total = len(df)
            positive = int((df["sentiment"] == "positive").sum())
            negative = int((df["sentiment"] == "negative").sum())
            mixed = int((df["sentiment"] == "mixed").sum())
            pending = int(df["complaint_status"].isin(["pending", "in_progress"]).sum())
            c1,c2,c3,c4,c5 = st.columns(5)
            c1.metric("Total Reviews", total)
            c2.metric("Positive", positive)
            c3.metric("Negative", negative)
            c4.metric("Mixed", mixed)
            c5.metric("Open Complaints", pending)
            st.subheader("Sentiment distribution")
            counts = df["sentiment"].value_counts().reindex(["positive","negative","mixed","neutral"], fill_value=0)
            st.bar_chart(counts)
            st.subheader("Recent feedback")
            cols = [c for c in ["created_at","branch_id","review_text","sentiment","category","complaint_status","source"] if c in df.columns]
            st.dataframe(df[cols].head(15), use_container_width=True, hide_index=True)
        elif page == "All Reviews":
            st.subheader("All Reviews")
            f1,f2,f3 = st.columns(3)
            sentiments = ["All"] + sorted(df["sentiment"].dropna().unique().tolist())
            selected_sentiment = f1.selectbox("Sentiment", sentiments)
            categories = ["All"] + sorted(df["category"].dropna().unique().tolist())
            selected_category = f2.selectbox("Category", categories)
            query = f3.text_input("Search feedback")
            filtered = df.copy()
            if selected_sentiment != "All":
                filtered = filtered[filtered["sentiment"] == selected_sentiment]
            if selected_category != "All":
                filtered = filtered[filtered["category"] == selected_category]
            if query:
                filtered = filtered[filtered["review_text"].astype(str).str.contains(query, case=False, na=False)]
            cols = [c for c in ["id","created_at","branch_id","review_text","sentiment","category","ai_summary","complaint_status","source"] if c in filtered.columns]
            st.dataframe(filtered[cols], use_container_width=True, hide_index=True)
        elif page == "Complaints":
            st.subheader("Complaint management")
            complaints = df[df["sentiment"].isin(["negative","mixed"])].copy()
            if complaints.empty:
                st.success("No negative or mixed reviews currently recorded.")
            else:
                st.dataframe(complaints[[c for c in ["id","created_at","branch_id","review_text","sentiment","category","ai_summary","complaint_status"] if c in complaints.columns]],
                             use_container_width=True, hide_index=True)
                st.markdown("#### Update complaint status")
                ids = complaints["id"].tolist()
                selected_id = st.selectbox("Review ID", ids)
                current = str(complaints.loc[complaints["id"] == selected_id, "complaint_status"].iloc[0])
                statuses = ["pending","in_progress","resolved"]
                selected_status = st.selectbox("New status", statuses, index=statuses.index(current) if current in statuses else 0)
                if st.button("Save status"):
                    update_review_status(selected_id, selected_status)
                    st.success("Complaint status updated. Refresh the page to see the latest value.")
        elif page == "Reports":
            st.subheader("Feedback report")
            counts = df["sentiment"].value_counts()
            st.write("Sentiment breakdown")
            st.dataframe(counts.rename_axis("sentiment").reset_index(name="reviews"), use_container_width=True, hide_index=True)
            st.write("Most common categories")
            st.dataframe(df["category"].value_counts().rename_axis("category").reset_index(name="reviews"),
                         use_container_width=True, hide_index=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download reviews CSV", csv, file_name="niloufer_reviews.csv", mime="text/csv")
            st.caption("Only export or share reports with authorized staff. Remove direct identifiers before broad sharing.")
