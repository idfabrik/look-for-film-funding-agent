import os
import requests
import socket
import requests.packages.urllib3.util.connection as urllib3_cn
from crewai import Agent, Task, Crew
from dotenv import load_dotenv
from tools.smtp_email_tool import smtp_email_sender
import gspread
from google.oauth2.service_account import Credentials
import re

# --- Force IPv4 only ---
def allowed_gai_family():
    return socket.AF_INET
urllib3_cn.allowed_gai_family = allowed_gai_family

# --- Load environment variables ---
load_dotenv()

# --- Google Sheets configuration ---
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
SPREADSHEET_ID = '1tPTgSOLZxXQkBs0e5r_RuAmE6GODI1qgq_g7RFTELSE'

# --- Search configuration (reduced) ---
SEARCH_QUERIES = [
    # Priority searches France
    # "financement film documentaire 2025 2026 France CNC aide cinema",
    # "subvention documentaire fiction serie France 2025 2026",
    # "coproduction internationale France Afrique cinema 2025 2026",
    "aide production audiovisuelle 2025 2026",
    
    # Priority searches Germany
    #"film funding Germany documentary fiction 2025 2026 Filmförderung",
    #"German film funding international coproduction Africa 2025 2026",
    #"Filmförderungsanstalt FFA documentary funding 2025 2026",
    #"German French coproduction film funding 2025 2026",
    
    # Specific searches Benin/Africa
    #"film funding Africa Benin documentary fiction 2025 2026",
    #"African cinema funding international coproduction 2025 2026",
    #"francophone film funding Africa documentary 2025 2026",
    
    # Thematic searches
    #"documentary funding political subjects Africa 2025 2026",
    #"cultural documentary funding voodoo traditional beliefs 2025",
    #"international coproduction funding documentary series 2025 2026",
    
    # European searches
    #"European film funding documentary fiction 2025 2026 Creative Europe",
    #"EU funding cinema coproduction Africa 2025 2026",
    
    # General searches
    #"film funding opportunities 2025 2026 documentary fiction",
    #"international film funding documentary series 2025 2026"
]

# --- Google Sheets functions ---
def get_google_sheet():
    """Initialize and return Google Sheets worksheet"""
    try:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        
        # Try to open main sheet, otherwise create new one
        try:
            sheet = spreadsheet.worksheet("Film Funding")
        except gspread.WorksheetNotFound:
            sheet = spreadsheet.add_worksheet(title="Film Funding", rows="1000", cols="13")
        
        return sheet
    except Exception as e:
        print(f"❌ Error initializing Google Sheets: {e}")
        return None

def setup_sheet_headers(sheet):
    """Configure column headers if they don't exist"""
    headers = [
        "Name", "Organization", "Country", "Deadline", "Link", 
        "Summary", "Email", "Conditions", "Category", "Year", 
        "Date Added", "Status", "Priority"
    ]
    
    try:
        # Check if first row already contains headers
        existing_headers = sheet.row_values(1)
        if not existing_headers or len(existing_headers) == 0:
            sheet.append_row(headers)
            print("✅ Headers added to sheet")
        else:
            # Add missing columns
            for i, header in enumerate(headers):
                if i >= len(existing_headers) or existing_headers[i] != header:
                    if i < len(existing_headers):
                        sheet.update_cell(1, i+1, header)
                    else:
                        # Extend header row
                        current_headers = sheet.row_values(1)
                        current_headers.extend(headers[len(current_headers):])
                        sheet.update('1:1', [current_headers])
                        break
    except Exception as e:
        print(f"⚠️ Error setting up headers: {e}")
        try:
            sheet.append_row(headers)
        except Exception as e2:
            print(f"❌ Failed to add headers: {e2}")

def categorize_funding(name, summary, organization):
    """Determine funding category"""
    text_to_analyze = f"{name} {summary} {organization}".lower()
    
    if any(word in text_to_analyze for word in ['series', 'tv', 'television']):
        return "Series"
    elif any(word in text_to_analyze for word in ['fiction', 'feature', 'long-métrage']):
        return "Fiction"
    elif any(word in text_to_analyze for word in ['documentary', 'documentaire', 'doc']):
        return "Documentary"
    else:
        return "General"

def determine_priority(country, organization):
    """Determine priority based on country"""
    text_to_check = f"{country} {organization}".lower()
    
    if any(word in text_to_check for word in ['france', 'français', 'cnc', 'french']):
        return "High - France"
    elif any(word in text_to_check for word in ['germany', 'german', 'allemagne', 'deutschland', 'ffa']):
        return "High - Germany"
    elif any(word in text_to_check for word in ['benin', 'bénin', 'africa', 'afrique']):
        return "Medium - Africa"
    elif any(word in text_to_check for word in ['europe', 'eu', 'creative']):
        return "Medium - Europe"
    else:
        return "Normal"

def extract_year(deadline, summary):
    """Extract year from deadline or summary"""
    text_to_check = f"{deadline} {summary}"
    
    if '2025' in text_to_check:
        return "2025"
    elif '2026' in text_to_check:
        return "2026"
    elif any(word in text_to_check.lower() for word in ['2025', '2026']):
        return "2025-2026"
    else:
        return "Not specified"

def get_existing_entries(sheet):
    """Get existing entries to avoid duplicates"""
    try:
        records = sheet.get_all_records()
        existing = set()
        for record in records:
            name = record.get('Name', '').strip()
            link = record.get('Link', '').strip()
            if name and link:
                existing.add((name.lower(), link))
        return existing
    except Exception as e:
        print(f"⚠️ Error retrieving existing entries: {e}")
        return set()

def send_to_google_sheets(funding_data):
    """Send data to Google Sheets"""
    try:
        sheet = get_google_sheet()
        if not sheet:
            print("❌ Failed to get Google Sheet")
            return False
            
        setup_sheet_headers(sheet)
        existing_entries = get_existing_entries(sheet)
        
        added_count = 0
        duplicate_count = 0
        
        for entry in funding_data:
            name = entry.get('name', '').strip()
            link = entry.get('link', '').strip()
            
            # Check for duplicates
            if (name.lower(), link) in existing_entries:
                duplicate_count += 1
                print(f"⏭️ Duplicate ignored: {name}")
                continue
            
            # Determine category, year and priority
            category = categorize_funding(entry.get('name', ''), entry.get('summary', ''), entry.get('organization', ''))
            year = extract_year(entry.get('deadline', ''), entry.get('summary', ''))
            priority = determine_priority(entry.get('country', ''), entry.get('organization', ''))
            
            # Prepare data row
            from datetime import datetime
            row_data = [
                entry.get('name', ''),
                entry.get('organization', ''),
                entry.get('country', ''),
                entry.get('deadline', ''),
                entry.get('link', ''),
                entry.get('summary', ''),
                entry.get('email', ''),
                entry.get('conditions', ''),
                category,
                year,
                datetime.now().strftime('%Y-%m-%d %H:%M'),
                'New',
                priority
            ]
            
            try:
                sheet.append_row(row_data)
                added_count += 1
                print(f"✅ Added: {name}")
            except Exception as e:
                print(f"❌ Error adding {name}: {e}")
        
        print(f"\n📊 Google Sheets Summary:")
        print(f"   - {added_count} new entries added")
        print(f"   - {duplicate_count} duplicates ignored")
        
        return True
        
    except Exception as e:
        print(f"❌ Google Sheets Error: {e}")
        return False

# --- Google Search API Wrapper ---
def google_search(query):
    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        raise ValueError("❌ GOOGLE_API_KEY or GOOGLE_CSE_ID is not set in the environment.")
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cse_id,
        "q": query
    }
    print("🔐 API Key:", api_key[:10] + "...")  # Only show first 10 chars for security
    print("🔍 CSE ID:", cse_id[:10] + "...")   # Only show first 10 chars for security
    print("📡 Query:", query)
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return [item["link"] for item in data.get("items", [])]

# --- VerifyBot API Wrapper ---
def extract_page_content(url):
    CONTENT_API_KEY = os.getenv("VERIFYBOT_CONTENT_API_KEY")
    if not CONTENT_API_KEY:
        raise ValueError("❌ VERIFYBOT_CONTENT_API_KEY not set in the environment.")
    api_url = "https://cockpit.verifybot.app/api-get-content.php"
    params = {
        "url": url,
        "key": CONTENT_API_KEY
    }
    response = requests.get(api_url, params=params)
    response.raise_for_status()
    data = response.json()
    return data.get("content") or data.get("summary") or "No summary available."

# --- Function to parse results ---
def parse_funding_results(result_text):
    """Parse result text to extract structured data"""
    funding_entries = []
    
    # Try different regex patterns to capture data
    patterns = [
        # Main pattern with all fields
        r"Name\s*:\s*(.*?)\s*Organization\s*:\s*(.*?)\s*Country\s*:\s*(.*?)\s*Deadline\s*:\s*(.*?)\s*Link\s*:\s*(.*?)\s*Summary\s*:\s*(.*?)\s*Email\s*:\s*(.*?)\s*Conditions\s*:\s*(.*?)(?=Name\s*:|$)",
        # Alternative pattern without some fields
        r"Name\s*:\s*(.*?)\s*Organization\s*:\s*(.*?)\s*Country\s*:\s*(.*?)\s*Link\s*:\s*(.*?)\s*Summary\s*:\s*(.*?)(?=Name\s*:|$)",
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, result_text, re.DOTALL | re.IGNORECASE)
        
        for match in matches:
            if len(match) >= 5:  # Minimum: name, organization, country, link, summary
                entry = {
                    "name": match[0].strip(),
                    "organization": match[1].strip(),
                    "country": match[2].strip(),
                    "deadline": match[3].strip() if len(match) > 3 else "",
                    "link": match[4].strip() if len(match) > 4 else match[3].strip(),
                    "summary": match[5].strip() if len(match) > 5 else match[4].strip(),
                    "email": match[6].strip() if len(match) > 6 else "",
                    "conditions": match[7].strip() if len(match) > 7 else ""
                }
                
                # Clean data
                for key, value in entry.items():
                    entry[key] = re.sub(r'\*\*', '', value)  # Remove **
                    entry[key] = re.sub(r'[\(\)]+', '', entry[key])  # Remove excessive parentheses
                    entry[key] = entry[key].strip()
                
                if entry["name"] and entry["organization"]:  # Check essential fields exist
                    funding_entries.append(entry)
        
        if funding_entries:  # If we found entries, stop
            break
    
    # If no pattern works, try simpler approach
    if not funding_entries:
        lines = result_text.split('\n')
        current_entry = {}
        
        for line in lines:
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if 'name' in key:
                    if current_entry and current_entry.get('name'):
                        funding_entries.append(current_entry)
                    current_entry = {'name': value}
                elif 'organization' in key:
                    current_entry['organization'] = value
                elif 'country' in key:
                    current_entry['country'] = value
                elif 'deadline' in key:
                    current_entry['deadline'] = value
                elif 'link' in key:
                    current_entry['link'] = value
                elif 'summary' in key:
                    current_entry['summary'] = value
                elif 'email' in key:
                    current_entry['email'] = value
                elif 'condition' in key:
                    current_entry['conditions'] = value
        
        if current_entry and current_entry.get('name'):
            funding_entries.append(current_entry)
    
    return funding_entries

# --- Agents ---
search_agent = Agent(
    role="Film funding specialist France-Germany-Africa",
    goal="Identify funding opportunities for documentaries, fiction and series, priority France-Germany, for project filmed in Benin about voodoo and politics.",
    backstory=(
        "Expert in international co-productions France-Germany-Africa, specialized in documentary "
        "and fiction projects addressing African cultural and political subjects."
    ),
    verbose=True,
)

data_cleaning_agent = Agent(
    role="Data cleaner",
    goal="Clean, standardize and reformulate collected information to create a usable database in a spreadsheet, without superfluous formatting or markdown elements.",
    backstory="Specialist in data normalization for structured databases.",
    verbose=True,
)

# --- Enhanced research function ---
def funding_research_task():
    print("🔍 Performing Google searches...")
    all_opportunities = []
    
    for i, query in enumerate(SEARCH_QUERIES, 1):
        print(f"\n🎯 Search {i}/{len(SEARCH_QUERIES)}: {query}")
        try:
            urls = google_search(query)
            print(f"🔗 Found {len(urls)} URLs")
            
            # Process fewer URLs per query to reduce time (5 instead of 10)
            for j, url in enumerate(urls[:5]):
                print(f"📄 Reading {j+1}/5: {url}")
                try:
                    summary = extract_page_content(url)
                    all_opportunities.append(f"---\nQuery: {query}\nURL: {url}\n{summary}")
                except Exception as e:
                    print(f"⚠️ Extraction error {url}: {e}")
                    continue
        except Exception as e:
            print(f"❌ Search error '{query}': {e}")
            continue
    
    print(f"\n✅ Total: {len(all_opportunities)} contents extracted")
    return "\n\n".join(all_opportunities)

# --- Tasks ---
search_task = Task(
    description=f"""Analyze collected web content and extract funding opportunities for:

TARGET PROJECT:
- Documentary/Fiction/Series about voodoo and politics in Benin
- France-Germany-Benin co-production
- Years 2025-2026

SEARCH PRIORITIES:
1. French funding (CNC, regional, etc.)
2. German funding (FFA, Länder, etc.) 
3. European funding (Creative Europe, etc.)
4. International Africa-Europe funding

For each funding opportunity, provide these EXACT fields:
- Name: Official name of the funding
- Organization: Organization offering the funding
- Country: Country or region of the organization
- Deadline: Application deadline (2025/2026)
- Link: Direct URL to the funding page
- Summary: Short description (2-3 sentences)
- Email: Contact email if available
- Conditions: Key eligibility criteria

Content to analyze:
{funding_research_task()}""",
    expected_output="Structured list of funding opportunities with fields: Name, Organization, Country, Deadline, Link, Summary, Email, Conditions. Priority to France-Germany funding 2025-2026.",
    agent=search_agent,
)

# Cleaning task
data_cleaning_task = Task(
    description="""Clean and structure data for documentary/fiction project in Benin:

CLEANING:
- Remove unnecessary characters (**...**, superfluous parentheses)
- Fix email and link formats
- Reformulate summaries that are too long (max 2-3 sentences)
- Identify if funding concerns: Documentary/Fiction/Series

PRIORITIZATION:
- Mark France and Germany funding as priority
- Identify 2025 and 2026 funding
- Flag international co-production specific funding

FINAL STRUCTURE:
Required fields: Name, Organization, Country, Deadline, Link, Summary, Email, Conditions
Result ready for spreadsheet with automatic classification.""",
    expected_output="Clean and classified version (Documentary/Fiction/Series) with France-Germany priorities identified",
    agent=data_cleaning_agent
)

# --- Crew ---
crew = Crew(
    agents=[search_agent, data_cleaning_agent],
    tasks=[search_task, data_cleaning_task],
    verbose=True,
)

# --- Run ---
print("🚀 Starting funding research and cleaning tasks...")
try:
    result = crew.kickoff()
    
    # Extract final result
    if hasattr(result, 'raw') and isinstance(result.raw, str):
        final_content = result.raw
    else:
        final_content = str(result)
        
except Exception as e:
    print("❌ Error during crew execution:", str(e))
    final_content = "No results due to error."

# --- Parse and send to Google Sheets ---
print("📊 Parsing results for Google Sheets...")
funding_data = parse_funding_results(final_content)

if funding_data:
    print(f"📋 Found {len(funding_data)} funding opportunities")
    
    # Send to Google Sheets
    sheets_success = send_to_google_sheets(funding_data)
    
    if sheets_success:
        print("✅ Data successfully sent to Google Sheets!")
    else:
        print("❌ Failed to send data to Google Sheets")
else:
    print("⚠️ No structured funding data found to send to Google Sheets")

# --- Send email ---
email_subject = "🎬 Film Funding Opportunities - Cleaned Results"
to_email = os.getenv("EMAIL_RECIPIENT")

if to_email:
    print("📤 Sending email...")
    try:
        email_result = smtp_email_sender.invoke({
            "subject": email_subject,
            "content": final_content,
            "to_email": to_email
        })
        print("📧 Email result:", email_result)
    except Exception as e:
        print("❌ Failed to send email:", str(e))
else:
    print("⚠️ No email recipient configured, skipping email...")

print("\n✅ Script completed!")

# Optional: display result in console
print("\n" + "="*50)
print("CLEANED RESULTS:")
print("="*50)
print(final_content)

if funding_data:
    print("\n" + "="*50)
    print("STRUCTURED DATA FOR GOOGLE SHEETS:")
    print("="*50)
    for i, entry in enumerate(funding_data, 1):
        print(f"\n--- ENTRY {i} ---")
        for key, value in entry.items():
            print(f"{key.capitalize()}: {value}")
