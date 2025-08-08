import streamlit as st
import pandas as pd
import altair as alt
import json
import os
import requests
import base64
import time

st.set_page_config(layout="wide")

DRAFT_PICKS_FILE = 'draft_picks.json'

GITHUB_API_URL = "https://api.github.com/repos/zielaq26/FPLDraft/contents/draft_picks.json"

TOKEN = st.secrets["github_token"]  # Store your GitHub PAT in Streamlit secrets

RAW_URL = "https://raw.githubusercontent.com/zielaq26/FPLDraft/main/draft_picks.json"

def load_data():
    # Load the base CSV
    df = pd.read_csv('players_ranked.csv')
    return df

def get_file_sha():
    headers = {
        "Authorization": f"token {TOKEN}",
        "Cache-Control": "no-cache",
        "Accept": "application/vnd.github+json"
    }
    # Add a timestamp query param to bust cache
    url = f"{GITHUB_API_URL}?t={int(time.time())}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()['sha']
    elif response.status_code == 404:
        return None
    else:
        response.raise_for_status()

def save_draft_picks(draft_picks):
    # Convert keys (tuples) to strings, and values to native int or None
    json_dict = {}
    for k, v in draft_picks.items():
        key_str = f"{k[0]}_{k[1]}"
        if v is None:
            json_dict[key_str] = None
        else:
            json_dict[key_str] = int(v)  # Convert int64 -> int here

    content_str = json.dumps(json_dict, indent=2)
    content_b64 = base64.b64encode(content_str.encode()).decode()

    sha = get_file_sha()

    payload = {
        "message": "Update draft picks from Streamlit app",
        "content": content_b64,
        "branch": "main"
    }
    if sha:
        payload["sha"] = sha  # Needed to update existing file

    headers = {
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    response = requests.put(GITHUB_API_URL, headers=headers, json=payload)
    if response.status_code in [200, 201]:
        st.success("Draft picks saved to GitHub!")
    else:
        st.error(f"Failed to save draft picks: {response.status_code} {response.text}")

def load_draft_picks():
    headers = {"Authorization": f"token {TOKEN}"}
    try:
        response = requests.get(GITHUB_API_URL, headers=headers)
        if response.status_code == 200:
            data = response.json()
            content_b64 = data.get('content', '')
            if content_b64:
                # Decode base64 content to string
                content_str = base64.b64decode(content_b64).decode('utf-8')
                json_dict = json.loads(content_str)
            else:
                return {}
        else:
            st.warning(f"⚠️ Could not load draft picks from GitHub API (status {response.status_code}).")
            # fallback to local file
            if os.path.exists(DRAFT_PICKS_FILE):
                with open(DRAFT_PICKS_FILE, 'r') as f:
                    json_dict = json.load(f)
            else:
                return {}
    except Exception as e:
        st.warning(f"⚠️ Error loading draft picks: {e}")
        if os.path.exists(DRAFT_PICKS_FILE):
            try:
                with open(DRAFT_PICKS_FILE, 'r') as f:
                    json_dict = json.load(f)
            except Exception:
                return {}
        else:
            return {}

    result = {}
    for k, v in json_dict.items():
        try:
            key_tuple = tuple(map(int, k.split('_')))
        except Exception:
            continue
        result[key_tuple] = None if v is None else int(v)
    return result

def highlight_row(row):
    if row.get('drafted'):
        return ['background-color: lightgray; color: black'] * len(row)
    else:
        color_map = {
            'MID': '#337ab7',
            'FWD': '#3c763d',
            'DEF': '#8a6d3b',
            'GKP': '#a94442',
        }
        bg_color = color_map.get(row['position'], '#222222')
        return [f'background-color: {bg_color}; color: white;'] * len(row)

def get_current_team_map():
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(url)
    data = response.json()
    teams = data['teams']
    return {team['id']: team['name'] for team in teams}

team_map = get_current_team_map()

position_colors = {
    'MID': '#337ab7',
    'FWD': '#3c763d',
    'DEF': '#8a6d3b',
    'GKP': '#a94442',
}

def prepare_draft_order(participants, rounds):
    order = []
    order += [(1, i+1, p) for i, p in enumerate(participants)]
    order += [(2, i+1, p) for i, p in enumerate(participants[::-1])]
    direction = 1
    for r in range(3, rounds + 1):
        if direction == 1:
            order += [(r, i+1, p) for i, p in enumerate(participants[::-1])]
        else:
            order += [(r, i+1, p) for i, p in enumerate(participants)]
        direction *= -1
    return order

def init_session_state(order):
    saved_picks = load_draft_picks()
    if "draft_picks" not in st.session_state:
        st.session_state.draft_picks = {(r, p): saved_picks.get((r, p), None) for (r, _, p) in order}
    if "current_pick_index" not in st.session_state:
        filled_indices = [i for i, (r, _, p) in enumerate(order) if st.session_state.draft_picks.get((r, p)) is not None]
        st.session_state.current_pick_index = max(filled_indices) + 1 if filled_indices else 0

df = load_data()
df['team_name'] = df['team'].map(team_map)
df['my_rank'] = df['my_rank'].fillna(0).astype(int)
df['tier'] = df['tier'].fillna(0).astype(int)

participants = [1, 2, 3, 4, 5, 6]
rounds = 15
order = prepare_draft_order(participants, rounds)
init_session_state(order)

st.sidebar.title("Navigation")

selected_player_ids = [pid for pid in st.session_state.draft_picks.values() if pid is not None]

st.title("Fantasy Football Dashboard")

st.sidebar.header("Filter players")
positions = ["All", "GKP", "DEF", "MID", "FWD"]
selected_position = st.sidebar.selectbox("Position", positions, key="dash_position")
teams = ["All"] + sorted(df['team_name'].unique())
selected_team = st.sidebar.selectbox("Team", teams, key="dash_team")
hide_drafted = st.sidebar.checkbox("Hide drafted players", value=False, key="hide_drafted")

filtered_df = df.copy()
if selected_position != "All":
    filtered_df = filtered_df[filtered_df['position'] == selected_position]
if selected_team != "All":
    filtered_df = filtered_df[filtered_df['team_name'] == selected_team]
if hide_drafted:
    filtered_df = filtered_df[~filtered_df['id'].isin(selected_player_ids)]

filtered_df = filtered_df.sort_values(by='my_rank')

undrafted_df = filtered_df[~filtered_df['id'].isin(selected_player_ids)]

top10 = undrafted_df.sort_values(by='var', ascending=False).head(10)

if not top10.empty:
    top10['color'] = top10['position'].map(position_colors)
    chart = (
        alt.Chart(top10)
        .mark_bar()
        .encode(
            x=alt.X('var:Q', title='VAR per game'),
            y=alt.Y('web_name:N', sort='-x', title='Player'),
            color=alt.Color('position:N',
                            scale=alt.Scale(domain=list(position_colors.keys()),
                                            range=list(position_colors.values())),
                            legend=None),
            tooltip=['web_name', 'position', 'var']
        )
        .properties(height=400)
    )
    st.subheader("Top 10 Available Players by VAR per Game")
    st.altair_chart(chart, use_container_width=True)
else:
    st.info("No available players to show in Top 10 chart.")

display_df = filtered_df.copy()

display_df['drafted'] = display_df['id'].isin(selected_player_ids)

display_df = display_df.drop(columns=['first_name', 'second_name', 'now_cost', 'value_season',
                                      'selected_by_percent', 'form', 'bps', 'status',
                                      'chance_of_playing_next_round', 'news', 'team', 'id', 'element_type', 'points_per_game'])

display_df = display_df.reset_index(drop=True)
display_df.index += 1

cols = display_df.columns.tolist()
new_order = ['tier', 'my_rank', 'draft_rank', 'web_name', 'position', 'team_name'] + \
            [col for col in cols if col not in ['tier', 'my_rank', 'draft_rank', 'web_name', 'position', 'team_name']]
display_df = display_df[new_order]

styled_df = display_df.style.apply(highlight_row, axis=1)
st.subheader("All Players")
st.dataframe(styled_df, use_container_width=True)