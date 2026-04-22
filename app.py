import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont, ImageOps
from datetime import datetime
import textwrap
import io
import requests
import base64
import urllib.parse

st.title("ChatJournal 📝")
st.write("Drop your thoughts or photos below.")

# === Configuration and State ===
if "messages" not in st.session_state:
    st.session_state.messages = []
if "app_stage" not in st.session_state:
    st.session_state.app_stage = "gathering"
if "draft_text" not in st.session_state:
    st.session_state.draft_text = ""
if "user_city" not in st.session_state:
    st.session_state.user_city = "" # Starts blank or you could default to "Canberra"
if "weather_str" not in st.session_state:
    st.session_state.weather_str = None

st.sidebar.title("App Settings")

# Try to load the API key from Streamlit's secure secrets vault
try:
    api_key = st.secrets["GEMINI_API_KEY"]
except KeyError:
    # Fallback just in case the secret hasn't been set up yet
    api_key = ""
    st.sidebar.error("API Key not found in Streamlit Secrets!")

# --- Location Settings ---
st.sidebar.markdown("### Location Context")

# By assigning the text box directly back to the session state, 
# your manual typing will now successfully override the auto-detect
new_city = st.sidebar.text_input("Your City", value=st.session_state.user_city)
st.session_state.user_city = new_city

# The auto-detect button
if st.sidebar.button("📍 Auto-Detect My City"):
    with st.spinner("Locating..."):
        try:
            # Trying ip-api.com, which sometimes handles Australian ISP routing better
            response = requests.get("http://ip-api.com/json/", timeout=5)
            data = response.json()
            
            if "city" in data:
                # Update the session state with the detected city
                st.session_state.user_city = data["city"]
                st.rerun() 
            else:
                st.sidebar.warning("Could not detect city. Please type it manually.")
        except Exception:
             st.sidebar.warning("Network error detecting location.")

hemisphere = st.sidebar.selectbox("Hemisphere", ["Southern", "Northern"])

# Helper for automatic date
today = datetime.now()
date_str = today.strftime("%d %B %Y")

# === STAGE 1: GATHERING ===
if st.session_state.app_stage == "gathering":
    
    if st.button("Synthesise Journal"):
        if not api_key:
            st.warning("Please enter your Gemini API key in the sidebar.")
        elif len(st.session_state.messages) == 0:
            st.info("Please send a few thoughts or photos first!")
        else:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            with st.spinner("Fetching local weather and synthesising your day..."):
                # 1. Fetch Live Weather Data (Strict Mode)
                target_city = st.session_state.user_city if st.session_state.user_city else "Canberra"
                safe_city = urllib.parse.quote(target_city)
                
                try:
                    weather_resp = requests.get(f"https://wttr.in/{safe_city}?format=%C,+%t", timeout=5)
                    weather_resp.raise_for_status() # Forces an error if the website is down
                    
                    # Explicitly tell Python to read the text as UTF-8 to fix the degree symbol
                    weather_resp.encoding = 'utf-8'
                    
                    st.session_state.weather_str = weather_resp.text.strip()
                except Exception as e:
                    # If it fails, show an error and immediately halt the app
                    st.error("Failed to fetch live weather data. The journal generation has been stopped.")
                    st.stop() 

                # Use the fetched weather for the text summary
                current_weather = st.session_state.weather_str

                # 2. Build the AI Instructions
                instructions = """You are a personal journal organiser, not a novelist.
Take the following text fragments and attached photos, and weave them into a single, cohesive, first-person diary entry.

Guidelines:
1. Tone & Style: Keep it casual, personal, and grounded. Do NOT use fancy, overly literary, or decorative words. Preserve my exact writing style and vocabulary.
2. Photos: Do not say 'I took a photo' or 'Here is a photo'. Look at the attached images and naturally describe what is happening as part of my day, merging them seamlessly with related text notes.
3. Emotional Accuracy: Do not invent new emotions. 
4. Flow: Connect thoughts simply without forcing chronological order."""

                content_to_send = [instructions]
                for msg in st.session_state.messages:
                    if msg["type"] == "text":
                        content_to_send.append(f"Note: {msg['content']}")
                    elif msg["type"] == "image":
                        content_to_send.append(msg["content"])
                
                # 3. Generate Content
                try:
                    response = model.generate_content(content_to_send)
                    
                    # Python handles the date and dynamic weather at the very end
                    formatted_journal = f"{response.text.strip()}\n\nDate: {date_str} | Weather: {current_weather} | City: {target_city}"
                    
                    # Save the draft and move to the review stage
                    st.session_state.draft_text = formatted_journal
                    st.session_state.app_stage = "reviewing"
                    st.rerun()
                except Exception as e:
                    st.error(f"An error occurred: {e}")

    st.divider()

    # Display chat with Edit and Delete options
    for i, message in enumerate(st.session_state.messages):
        with st.chat_message("user"):
            if message["type"] == "text":
                # Check if this specific message is in 'editing' mode
                edit_key = f"edit_{i}"
                if edit_key not in st.session_state:
                    st.session_state[edit_key] = False
                    
                if st.session_state[edit_key]:
                    # Show a text area to change the thought
                    new_text = st.text_area("Edit your thought:", value=message["content"], key=f"text_{i}")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Save", key=f"save_{i}"):
                            st.session_state.messages[i]["content"] = new_text
                            st.session_state[edit_key] = False
                            st.rerun()
                    with col2:
                        if st.button("Cancel", key=f"cancel_{i}"):
                            st.session_state[edit_key] = False
                            st.rerun()
                else:
                    # Show the normal text and action buttons
                    st.markdown(message["content"])
                    col1, col2, _ = st.columns([1, 1, 4])
                    with col1:
                        if st.button("Edit", key=f"edit_btn_{i}"):
                            st.session_state[edit_key] = True
                            st.rerun()
                    with col2:
                        if st.button("Delete", key=f"del_txt_{i}"):
                            st.session_state.messages.pop(i)
                            st.rerun()

            elif message["type"] == "image":
                st.image(message["content"], width=300)
                # Images just need a delete button
                if st.button("Delete Photo", key=f"del_img_{i}"):
                    st.session_state.messages.pop(i)
                    st.rerun()

    # The Attachment Menu 
    with st.popover("➕ Photo"):
        uploaded_file = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png"])
        
        if uploaded_file is not None:
            if st.button("Send Photo"):
                img = Image.open(uploaded_file)
                # This single line reads the phone sensor data and rotates the photo upright
                img = ImageOps.exif_transpose(img)
                st.session_state.messages.append({"role": "user", "type": "image", "content": img})
                st.rerun()

    if prompt := st.chat_input("Type a thought, paste a music link, or log an event..."):
        st.session_state.messages.append({"role": "user", "type": "text", "content": prompt})
        st.rerun()

# === STAGE 2: REVIEWING ===
elif st.session_state.app_stage == "reviewing":
    st.subheader("Review your journal")
    st.write("Make any changes to the text below before we generate your final page.")
    
    # User can edit the text directly in this box
    edited_text = st.text_area("Your Draft", value=st.session_state.draft_text, height=300)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancel & Go Back"):
            st.session_state.app_stage = "gathering"
            st.rerun()
    with col2:
        if st.button("Finalise & Generate Page", type="primary"):
            st.session_state.draft_text = edited_text
            st.session_state.app_stage = "finalised"
            st.rerun()

# === STAGE 3: FINALISED (IMAGE GENERATION) ===
elif st.session_state.app_stage == "finalised":
    st.subheader("Creating your masterpiece...")
    
    with st.spinner("Drawing your journal canvas..."):
        try:
            # 1. Dynamic Canvas Generation based on Location, Season, and Weather
            current_month = datetime.now().month
            location = "Canberra"
            
            # Determine Southern Hemisphere season and assign a visual theme
            if current_month in [12, 1, 2]:
                season = "Summer"
                theme = "sunflowers and bright green summer leaves"
            elif current_month in [3, 4, 5]:
                season = "Autumn"
                theme = "autumn leaves in rich orange, red, and brown tones"
            elif current_month in [6, 7, 8]:
                season = "Winter"
                theme = "bare winter branches and cool blue frost"
            else:
                season = "Spring"
                theme = "spring blossoms and fresh light greenery"
            
            # Clean up the saved weather string to use in the prompt
            weather_condition = st.session_state.weather_str.split(',')[0]
            
            # Construct the dynamic prompt
            raw_prompt = f"A blank, textured cream-coloured journal page. The corners are decorated with subtle watercolour art of {theme}. The overall mood reflects a {weather_condition} in {location}. No text, no tables, perfectly blank paper in the centre."
            
            # Safely encode the prompt for a web URL
            safe_prompt = urllib.parse.quote(raw_prompt)
            url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=900&height=1200&nologo=true"
            
            response = requests.get(url)
            
            # FORCE the canvas to be exactly 900x1200
            canvas = Image.open(io.BytesIO(response.content)).convert("RGBA").resize((900, 1200))
            draw = ImageDraw.Draw(canvas)
            
            # 2. The 3/5 and 2/5 Proportional Grid System
            page_width = 900
            page_height = 1200
            
            margin_left = 150  
            margin_right = 150 
            margin_y = 200  
            bottom_margin = 150  
            
            usable_width = page_width - margin_left - margin_right

            has_photo = any(msg["type"] == "image" for msg in st.session_state.messages)
            
            # SAFE, PROPORTIONAL COLUMN STRUCTURE
            if has_photo:
                # 3/5 (60%) for text, minus 20px to create a visual gap
                text_col_width = int(usable_width * 0.6) - 20 
                # 2/5 (40%) for photos
                photo_col_width = int(usable_width * 0.4)
                # Photos start exactly where the text section ends
                photo_x_pos = margin_left + int(usable_width * 0.6) 
            else:
                text_col_width = usable_width
            
            # 3. Pixel-Perfect Text Wrapping Function
            def get_wrapped_text(text, font, max_pixels):
                wrapped_lines = []
                for paragraph in text.split('\n'):
                    if not paragraph.strip():
                        wrapped_lines.append("")
                        continue
                    words = paragraph.split()
                    current_line = ""
                    for word in words:
                        test_line = current_line + word + " " if current_line else word + " "
                        if draw.textlength(test_line, font=font) <= max_pixels:
                            current_line = test_line
                        else:
                            if current_line:
                                wrapped_lines.append(current_line.strip())
                            current_line = word + " "
                    if current_line:
                        wrapped_lines.append(current_line.strip())
                return "\n".join(wrapped_lines)

            # 4. The "Auto-Fit and Polish" Font Algorithm
            try:
                font_size = 72 
                
                # Step A: Find the largest fitting size vertically
                while font_size > 14:
                    font = ImageFont.truetype("journal_font.ttf", font_size)
                    wrapped_text = get_wrapped_text(st.session_state.draft_text, font, text_col_width)
                    
                    bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
                    text_height = bbox[3] - bbox[1]
                    
                    if text_height <= (page_height - margin_y - bottom_margin):
                        break 
                    font_size -= 2
                    
                # Step B: SHRINK by exactly 2 points
                font_size = max(14, font_size - 2)
                
                font = ImageFont.truetype("journal_font.ttf", font_size)
                wrapped_text = get_wrapped_text(st.session_state.draft_text, font, text_col_width)
                    
            except IOError:
                font = ImageFont.load_default()
                wrapped_text = textwrap.fill(st.session_state.draft_text, width=30 if has_photo else 60)
                st.warning("Could not find journal_font.ttf! Make sure it is in the same folder as app.py.")

            # 5. Draw the text
            draw.text((margin_left, margin_y), wrapped_text, fill=(40, 40, 40), font=font)
            
            # 6. Draw the Photos dynamically sharing vertical space
            if has_photo:
                photo_y_pos = margin_y 
                
                photo_messages = [msg for msg in st.session_state.messages if msg["type"] == "image"]
                num_photos = len(photo_messages)
                
                available_height = page_height - margin_y - bottom_margin
                total_gaps = (num_photos - 1) * 30 if num_photos > 1 else 0
                max_h_per_photo = (available_height - total_gaps) // num_photos
                
                for msg in photo_messages:
                    user_photo = msg["content"].copy()
                    
                    target_w = photo_col_width - 16
                    target_h = min(500, max_h_per_photo) 
                    
                    user_photo.thumbnail((target_w, target_h))
                    
                    actual_w, actual_h = user_photo.size
                    bordered_photo = Image.new("RGBA", (actual_w + 16, actual_h + 16), (255, 255, 255, 255))
                    bordered_photo.paste(user_photo, (8, 8))
                    
                    canvas.paste(bordered_photo, (int(photo_x_pos), int(photo_y_pos)))
                    
                    photo_y_pos += bordered_photo.height + 30
            
            # 7. Display the final result
            st.success("Your journal page is ready!")
            st.image(canvas)
            
            # Use columns to place the buttons side-by-side
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("Go Back & Edit Text"):
                    st.session_state.app_stage = "reviewing"
                    st.rerun()
                    
            with col2:
                if st.button("Start a New Day", type="primary"):
                    st.session_state.messages = []
                    st.session_state.draft_text = ""
                    st.session_state.app_stage = "gathering"
                    st.rerun()
                
        except Exception as e:
            st.error(f"Image generation failed: {e}")
            if st.button("Go Back"):
                st.session_state.app_stage = "reviewing"
                st.rerun()
