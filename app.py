import os
import streamlit as st
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
from auth.db import (
    init_db, create_user, get_user, check_password,
    mark_verified, generate_code, verify_code,
    increment_essays, get_essays_used,
    increment_research, get_research_used,
    create_session, validate_session,
    save_session_data, load_session_data,
    save_essay_history, get_essay_history,
)
from auth.mailer import send_verification_code
from auth.gate import (
    is_edu_email, get_available_tiers, can_write_essay, essays_remaining,
    can_run_research, research_remaining, is_admin,
)
import config
from agents.researcher import (
    first_question, next_question, make_search_query, build_brief,
    discover_research_gaps, first_question_research, next_question_research, build_research_brief,
)
from agents.writer import write_draft, revise_draft, write_research_paper, revise_research_paper
from agents.critic import critique_draft, critique_research_paper
from tools.search import search_web
from tools.file_reader import extract_all, process_resources

st.set_page_config(page_title="Ideios", layout="centered")

init_db()

STAGES = ["auth", "verify", "topic", "research", "generating", "done"]
STAGE_LABELS = {
    "auth":       "Sign In",
    "verify":     "Verify",
    "topic":      "Topic",
    "research":   "Interview",
    "generating": "Writing...",
    "done":       "Essay",
}

MAX_FILES = 3
MAX_FILE_MB = 10
MIN_TURNS_TO_WRITE = 5
HARD_LIMIT = 25
WARN_AT = 20


def init():
    defaults = {
        "stage": "auth",
        "email": "",
        "tier": None,
        "models": config.get_models(False),
        "topic": "",
        "resources": "",
        "conversation": [],
        "result": None,
        "pending_email": "",
        "session_token": "",
        "mode": "essay",
        "research_area": "",
        "discovered_gaps": [],
        "selected_gap": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def go_to(stage: str):
    st.session_state.stage = stage
    st.rerun()


def set_models_for_user(email: str, tier: str):
    paid = is_admin(email) or tier != "free"
    st.session_state.models = config.get_models(paid)


def validate_files(files):
    if not files:
        return [], None
    if len(files) > MAX_FILES:
        return [], f"Please upload no more than {MAX_FILES} files."
    oversized = [f.name for f in files if f.size > MAX_FILE_MB * 1024 * 1024]
    if oversized:
        return [], f"These files exceed the {MAX_FILE_MB}MB limit: {', '.join(oversized)}"
    return files, None


init()

# ── Session guard — force sign out if another device logged in ────────────────
if st.session_state.stage not in ("auth", "verify") and st.session_state.session_token:
    if not validate_session(st.session_state.email, st.session_state.session_token):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.warning("You were signed out because your account was accessed from another device.")
        st.rerun()

# ── Sidebar navigation ────────────────────────────────────────────────────────
if st.session_state.stage not in ("auth", "verify"):
    with st.sidebar:
        st.markdown("### Ideios")
        st.divider()

        current = st.session_state.stage
        nav_stages = ["topic", "research", "done"]
        visited = STAGES[:STAGES.index(current) + 1]

        for s in nav_stages:
            label = STAGE_LABELS[s]
            if s == current:
                st.markdown(f"**→ {label}**")
            elif s in visited or (s == "done" and st.session_state.result):
                if st.button(label, key=f"nav_{s}"):
                    go_to(s)
            else:
                st.markdown(f"<span style='color:gray'>{label}</span>", unsafe_allow_html=True)

        st.divider()
        st.caption(st.session_state.email)
        essays_used = get_essays_used(st.session_state.email)
        remaining = essays_remaining(st.session_state.tier, essays_used, st.session_state.email)
        st.caption(f"{remaining} essays remaining")
        r_used = get_research_used(st.session_state.email)
        r_remaining = research_remaining(st.session_state.tier, r_used, st.session_state.email)
        if config.RESEARCH_LIMITS.get(st.session_state.tier, 0) > 0:
            st.caption(f"{r_remaining} research runs remaining")

        if st.session_state.tier == "free":
            st.markdown("---")
            st.markdown("**✦ Upgrade to Premium**")
            st.caption("Unlock Claude Opus · 10 essays/month · deeper interviews")

        if st.button("Sign out"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

# ── Auth (Sign In / Sign Up) ──────────────────────────────────────────────────
if st.session_state.stage == "auth":
    st.title("Ideios")
    st.caption("Think deeper. Write better.")
    st.divider()

    tab_in, tab_up = st.tabs(["Sign In", "Sign Up"])

    # ── Sign In ──
    with tab_in:
        si_email = st.text_input("Email", key="si_email")
        si_password = st.text_input("Password", type="password", key="si_password")

        if st.button("Sign In", type="primary", key="btn_signin"):
            if not si_email or not si_password:
                st.error("Please enter your email and password.")
            else:
                user = get_user(si_email)
                if not user or not check_password(si_email, si_password):
                    st.error("Incorrect email or password.")
                elif not user["verified"]:
                    code = generate_code(si_email)
                    try:
                        send_verification_code(si_email, code)
                        st.session_state.pending_email = si_email.lower()
                        st.info("Your email isn't verified yet — we've sent a new code.")
                        go_to("verify")
                    except Exception:
                        st.error("Couldn't send verification email. Please check your connection.")
                else:
                    st.session_state.email = si_email.lower()
                    st.session_state.tier = user["tier"]
                    st.session_state.session_token = create_session(si_email)
                    set_models_for_user(si_email, user["tier"])
                    data = load_session_data(si_email)
                    st.session_state.topic = data["topic"]
                    st.session_state.resources = data["resources"]
                    st.session_state.conversation = data["conversation"]
                    st.session_state.result = data["result"]
                    st.session_state.mode = data["mode"]
                    st.session_state.research_area = data["research_area"]
                    go_to("topic")

    # ── Sign Up ──
    with tab_up:
        su_email = st.text_input("Email", key="su_email")
        su_password = st.text_input("Password (min 8 characters)", type="password", key="su_password")
        su_password2 = st.text_input("Confirm password", type="password", key="su_password2")

        if su_email:
            if is_edu_email(su_email):
                st.success("Student pricing unlocked with your .edu email.")
            else:
                st.info("Use a .edu email to access student pricing and a free trial.")
            # Show pricing as marketing — tier is assigned after payment (currently all start as free)
            tiers = get_available_tiers(su_email)
            st.selectbox(
                "Your plan after payment",
                options=list(tiers.keys()),
                format_func=lambda t: tiers[t],
                key="su_tier",
                help="Payment coming soon. All accounts start on the Free plan.",
            )

        if st.button("Create Account", type="primary", key="btn_signup"):
            if not su_email or not su_password or not su_password2:
                st.error("Please fill in all fields.")
            elif len(su_password) < 8:
                st.error("Password must be at least 8 characters.")
            elif su_password != su_password2:
                st.error("Passwords don't match.")
            elif not su_email:
                st.error("Please enter your email.")
            else:
                tier = "free" if is_edu_email(su_email) else "guest"
                created = create_user(su_email, su_password, tier)
                if not created:
                    st.error("An account with this email already exists. Please sign in.")
                else:
                    code = generate_code(su_email)
                    try:
                        send_verification_code(su_email, code)
                        st.session_state.pending_email = su_email.lower()
                        st.session_state.tier = "free"
                        go_to("verify")
                    except Exception:
                        st.error("Account created but couldn't send verification email. Please check your connection.")

# ── Verify ────────────────────────────────────────────────────────────────────
elif st.session_state.stage == "verify":
    st.title("Check your email")
    st.write(f"We sent a 6-digit code to **{st.session_state.pending_email}**. Enter it below.")
    st.caption("The code expires in 10 minutes.")
    st.divider()

    code_input = st.text_input("Verification code", max_chars=6, placeholder="123456")

    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("Verify", type="primary"):
            if verify_code(st.session_state.pending_email, code_input):
                mark_verified(st.session_state.pending_email)
                user = get_user(st.session_state.pending_email)
                st.session_state.email = st.session_state.pending_email
                st.session_state.tier = user["tier"]
                st.session_state.session_token = create_session(st.session_state.pending_email)
                set_models_for_user(st.session_state.pending_email, user["tier"])
                data = load_session_data(st.session_state.pending_email)
                st.session_state.topic = data["topic"]
                st.session_state.resources = data["resources"]
                st.session_state.conversation = data["conversation"]
                st.session_state.result = data["result"]
                st.session_state.mode = data["mode"]
                st.session_state.research_area = data["research_area"]
                st.success("Email verified! Welcome to Ideios.")
                go_to("topic")
            else:
                st.error("Incorrect or expired code. Please try again.")
    with col2:
        if st.button("Resend code"):
            code = generate_code(st.session_state.pending_email)
            try:
                send_verification_code(st.session_state.pending_email, code)
                st.success("New code sent.")
            except Exception:
                st.error("Couldn't send email. Please try again.")

# ── Topic ─────────────────────────────────────────────────────────────────────
elif st.session_state.stage == "topic":
    st.title("Ideios")

    tab_essay, tab_research = st.tabs(["Write an Essay", "Research Discovery"])

    # ── Essay tab ──
    with tab_essay:
        topic = st.text_area(
            "Describe your topic or paste your assignment prompt (max 500 words)",
            value=st.session_state.topic if st.session_state.mode == "essay" else "",
            height=130,
            placeholder="e.g. Should universities require students to study a foreign language?",
            max_chars=2500,
        )

        uploaded_files = st.file_uploader(
            f"Upload resources — optional (max {MAX_FILES} files, {MAX_FILE_MB}MB each · PDF, Word, TXT)",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
        )

        file_error = None
        if uploaded_files:
            valid_files, file_error = validate_files(uploaded_files)
            if file_error:
                st.error(file_error)
            else:
                st.success(f"{len(valid_files)} file(s) ready.")

        col1, col2 = st.columns([3, 1])
        with col1:
            start = st.button(
                "Start Interview →",
                type="primary",
                disabled=not topic.strip() or bool(file_error),
            )
        with col2:
            if st.session_state.conversation and st.session_state.mode == "essay":
                if st.button("Resume Interview"):
                    go_to("research")

        if start:
            essays_used = get_essays_used(st.session_state.email)
            if not can_write_essay(st.session_state.tier, essays_used, st.session_state.email):
                st.error("You've used all your essays this month. Please upgrade your plan.")
            else:
                st.session_state.mode = "essay"
                st.session_state.topic = topic.strip()
                valid_files, _ = validate_files(uploaded_files) if uploaded_files else ([], None)
                if valid_files:
                    try:
                        raw = extract_all(valid_files)
                        with st.spinner("Processing resources..."):
                            st.session_state.resources = process_resources(raw, topic.strip())
                    except Exception:
                        st.warning("We couldn't read one or more files — continuing without them. Try a .txt file or paste the content directly into your topic.")
                        st.session_state.resources = ""
                st.session_state.conversation = []
                try:
                    with st.spinner("Starting interview..."):
                        opening_q = first_question(topic.strip(), model=st.session_state.models["interview"])
                    st.session_state.conversation.append({"role": "assistant", "content": opening_q})
                    save_session_data(st.session_state.email, st.session_state.topic,
                                      st.session_state.resources, st.session_state.conversation, None,
                                      mode="essay", research_area="")
                    go_to("research")
                except Exception:
                    st.error("Hmm, something seems off — please try again in a moment.")

    # ── Research Discovery tab ──
    with tab_research:
        r_used = get_research_used(st.session_state.email)
        r_rem = research_remaining(st.session_state.tier, r_used, st.session_state.email)

        if config.RESEARCH_LIMITS.get(st.session_state.tier, 0) == 0:
            st.info("Research Discovery is available on paid plans. Upgrade to access.")
        else:
            st.caption(f"{r_rem} research run{'s' if r_rem != 1 else ''} remaining this month")
            st.write(
                "Describe a research area and we'll scan the literature, identify open problems, "
                "and help you develop one into a paper."
            )

            st.text_area(
                "Describe your research area",
                height=100,
                placeholder="e.g. Transformer architectures for protein structure prediction",
                key="research_area_input",
            )
            area_input = st.session_state.get("research_area_input", "").strip()

            col_disc, col_resume = st.columns([2, 1])
            with col_disc:
                discover_clicked = st.button(
                    "Discover gaps →",
                    type="primary",
                    disabled=not area_input,
                )
            with col_resume:
                if st.session_state.conversation and st.session_state.mode == "research":
                    if st.button("Resume research interview"):
                        go_to("research")

            if discover_clicked and area_input:
                with st.spinner("Scanning the literature — this takes about 15 seconds..."):
                    try:
                        gaps = discover_research_gaps(area_input,
                                                      model=st.session_state.models["brief"])
                        st.session_state.research_area = area_input
                        st.session_state.discovered_gaps = gaps
                        st.session_state.selected_gap = None
                    except Exception:
                        st.error("Couldn't reach the literature search — please try again.")

            if st.session_state.discovered_gaps:
                st.divider()
                st.subheader("Research gaps identified")
                gap_labels = [f"{g['title']}" for g in st.session_state.discovered_gaps]
                selected_idx = st.radio(
                    "Select a gap to develop into a paper:",
                    options=range(len(gap_labels)),
                    format_func=lambda i: gap_labels[i],
                    key="gap_radio",
                )
                gap = st.session_state.discovered_gaps[selected_idx]
                with st.expander("About this gap", expanded=True):
                    st.write(gap["description"])
                    st.caption(f"**Why it matters:** {gap['why_interesting']}")

                st.divider()
                if r_rem <= 0:
                    st.error("You've used all your research runs this month. Upgrade to continue.")
                else:
                    if st.button("Research this gap →", type="primary"):
                        st.session_state.mode = "research"
                        st.session_state.selected_gap = gap
                        st.session_state.topic = f"{gap['title']}: {gap['description']}"
                        st.session_state.resources = ""
                        st.session_state.conversation = []
                        try:
                            with st.spinner("Starting research interview..."):
                                opening_q = first_question_research(
                                    gap, st.session_state.research_area,
                                    model=st.session_state.models["interview"],
                                )
                            st.session_state.conversation.append(
                                {"role": "assistant", "content": opening_q}
                            )
                            save_session_data(
                                st.session_state.email, st.session_state.topic,
                                "", st.session_state.conversation, None,
                                mode="research",
                                research_area=st.session_state.research_area,
                            )
                            go_to("research")
                        except Exception:
                            st.error("Hmm, something seems off — please try again in a moment.")

    # ── History ──
    history = get_essay_history(st.session_state.email)
    if history:
        st.divider()
        st.subheader("Previous essays")
        for entry in history:
            date_str = entry["created_at"][:10]
            label = f"{date_str} — {entry['topic'][:80]}{'…' if len(entry['topic']) > 80 else ''}"
            with st.expander(label):
                st.markdown(entry["final_draft"])
                st.download_button(
                    "Download as .txt",
                    data=entry["final_draft"],
                    file_name=f"essay_{entry['id']}.txt",
                    mime="text/plain",
                    key=f"dl_{entry['id']}",
                )

# ── Research (live interview) ─────────────────────────────────────────────────
elif st.session_state.stage == "research":
    user_turns = [t for t in st.session_state.conversation if t["role"] == "user"]
    n = len(user_turns)
    at_limit = n >= HARD_LIMIT
    ready_to_write = n >= MIN_TURNS_TO_WRITE
    is_research_mode = st.session_state.mode == "research"

    st.title("Research Interview" if is_research_mode else "Interview")
    if at_limit:
        st.caption(f"Interview complete ({HARD_LIMIT}/{HARD_LIMIT} exchanges used).")
    else:
        st.caption(f"({n}/{HARD_LIMIT} exchanges)")

    if st.button("← Back to Topic"):
        go_to("topic")

    st.info("💡 A richer interview leads to a better essay. We recommend working through all five phases before writing.")

    if st.session_state.tier == "free":
        st.caption("✦ Free plan · Standard AI model — [Upgrade for deeper, more perceptive questions](#)")
    st.divider()

    for turn in st.session_state.conversation:
        with st.chat_message("assistant" if turn["role"] == "assistant" else "user"):
            st.markdown(turn["content"])

    if n >= WARN_AT and not at_limit:
        st.warning(f"You have {HARD_LIMIT - n} exchanges left — start wrapping up your thoughts.")

    if at_limit:
        st.error("You've reached the maximum interview length. Time to write your essay.")

    if user_turns:
        st.divider()
        if not ready_to_write:
            st.caption(f"Keep going — at least {MIN_TURNS_TO_WRITE} exchanges recommended. ({n}/{MIN_TURNS_TO_WRITE})")
        write_label = "I've said everything → Write my paper" if is_research_mode else "I've said everything → Write my essay"
        if st.button(
            write_label,
            type="primary",
            disabled=not ready_to_write and not at_limit,
        ):
            st.session_state.result = None  # force re-run even if a prior result exists
            go_to("generating")

    if not at_limit:
        user_input = st.chat_input("Your answer... (max 400 words)", max_chars=2000)
        if user_input:
            st.session_state.conversation.append({"role": "user", "content": user_input})
            try:
                with st.spinner(""):
                    if is_research_mode and st.session_state.selected_gap:
                        follow_up = next_question_research(
                            st.session_state.selected_gap,
                            st.session_state.research_area,
                            st.session_state.conversation,
                            model=st.session_state.models["interview"],
                        )
                    else:
                        follow_up = next_question(
                            st.session_state.topic, st.session_state.conversation,
                            model=st.session_state.models["interview"],
                        )
                st.session_state.conversation.append({"role": "assistant", "content": follow_up})
                save_session_data(
                    st.session_state.email, st.session_state.topic,
                    st.session_state.resources, st.session_state.conversation,
                    st.session_state.result,
                    mode=st.session_state.mode,
                    research_area=st.session_state.research_area,
                )
            except Exception:
                st.session_state.conversation.pop()
                st.error("Hmm, something seems off — please try again in a moment.")
            st.rerun()

# ── Generating ────────────────────────────────────────────────────────────────
elif st.session_state.stage == "generating":
    is_research_mode = st.session_state.mode == "research"
    st.title("Writing your paper..." if is_research_mode else "Writing your essay...")

    if st.session_state.result:
        go_to("done")

    m = st.session_state.models

    if is_research_mode:
        _research_used_now = get_research_used(st.session_state.email)
        if not can_run_research(st.session_state.tier, _research_used_now, st.session_state.email):
            st.error("You've used all your research runs this month. Please upgrade your plan.")
            if st.button("← Back"):
                go_to("topic")
            st.stop()
    else:
        _essays_used_now = get_essays_used(st.session_state.email)
        if not can_write_essay(st.session_state.tier, _essays_used_now, st.session_state.email):
            st.error("You've used all your essays this month. Please upgrade your plan.")
            if st.button("← Back"):
                go_to("topic")
            st.stop()

    try:
        if is_research_mode:
            with st.status("Building your research paper — this takes about 60–90 seconds.", expanded=True) as status:
                st.write("Generating search query...")
                query = make_search_query(st.session_state.topic, st.session_state.resources)

                st.write("Searching the literature...")
                search_results = search_web(query)

                st.write("Compiling research brief...")
                gap = st.session_state.selected_gap or {"title": st.session_state.topic, "description": ""}
                brief = build_research_brief(
                    gap, st.session_state.research_area,
                    st.session_state.conversation, st.session_state.resources,
                    search_results, model=m["brief"],
                )

                st.write("Writing first draft...")
                draft = write_research_paper(brief, model=m["writer"])

                st.write("Reviewing draft...")
                critique = critique_research_paper(draft, brief, model=m["critic"])

                st.write("Refining final paper...")
                final_draft = revise_research_paper(draft, critique, model=m["revise"])

                status.update(label="Paper complete!", state="complete")

            result = {"brief": brief, "draft": draft, "critique": critique, "final_draft": final_draft}
            st.session_state.result = result
            increment_research(st.session_state.email)
            save_essay_history(st.session_state.email, st.session_state.topic, result["final_draft"])
            save_session_data(
                st.session_state.email, st.session_state.topic,
                st.session_state.resources, st.session_state.conversation, result,
                mode="research", research_area=st.session_state.research_area,
            )
        else:
            with st.status("Working on your essay — this takes about 30–60 seconds.", expanded=True) as status:
                st.write("Generating search query...")
                query = make_search_query(st.session_state.topic, st.session_state.resources)

                st.write("Searching the web...")
                search_results = search_web(query)

                st.write("Compiling research brief...")
                brief = build_brief(st.session_state.topic, st.session_state.conversation,
                                    st.session_state.resources, search_results, model=m["brief"])

                st.write("Writing first draft...")
                draft = write_draft(brief, model=m["writer"])

                st.write("Reviewing draft...")
                critique = critique_draft(draft, brief, model=m["critic"])

                st.write("Refining final essay...")
                final_draft = revise_draft(draft, critique, model=m["revise"])

                status.update(label="Essay complete!", state="complete")

            result = {"brief": brief, "draft": draft, "critique": critique, "final_draft": final_draft}
            st.session_state.result = result
            increment_essays(st.session_state.email)
            save_essay_history(st.session_state.email, st.session_state.topic, result["final_draft"])
            save_session_data(
                st.session_state.email, st.session_state.topic,
                st.session_state.resources, st.session_state.conversation, result,
                mode="essay", research_area="",
            )

        go_to("done")
    except Exception as e:
        st.error("Looks like we hit a snag — please give it another shot.")
        if DEBUG:
            st.exception(e)
        if st.button("Try again"):
            st.rerun()

# ── Done ──────────────────────────────────────────────────────────────────────
elif st.session_state.stage == "done":
    result = st.session_state.result
    is_research_mode = st.session_state.mode == "research"
    essays_used = get_essays_used(st.session_state.email)
    remaining = essays_remaining(st.session_state.tier, essays_used, st.session_state.email)
    user_turns_done = len([t for t in st.session_state.conversation if t["role"] == "user"])

    st.title("Your Paper" if is_research_mode else "Your Essay")
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        if is_research_mode:
            r_used_done = get_research_used(st.session_state.email)
            r_rem_done = research_remaining(st.session_state.tier, r_used_done, st.session_state.email)
            st.caption(f"{r_rem_done} research runs remaining this month")
        else:
            st.caption(f"{remaining} essays remaining this month")
    with col_info2:
        st.caption("✓ Saved to your history")
    st.divider()

    st.markdown(result["final_draft"])

    if st.session_state.tier == "free":
        st.info(
            "**This essay was written with our standard model.** "
            "Upgrade to Premium and your next essay will be crafted by Claude Opus — "
            "Anthropic's most powerful model — for sharper arguments, richer prose, and deeper insight."
        )

    st.divider()

    st.download_button(
        "Download as .txt",
        data=result["final_draft"],
        file_name="paper.txt" if is_research_mode else "essay.txt",
        mime="text/plain",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        if user_turns_done < HARD_LIMIT:
            if st.button(f"Continue Interview ({user_turns_done}/{HARD_LIMIT})"):
                go_to("research")
        else:
            st.button(f"Interview complete ({HARD_LIMIT}/{HARD_LIMIT})", disabled=True)
    with col2:
        if st.button("← Back to Interview"):
            go_to("research")
    with col3:
        if st.button("Start something new"):
            st.session_state.topic = ""
            st.session_state.resources = ""
            st.session_state.conversation = []
            st.session_state.result = None
            st.session_state.mode = "essay"
            st.session_state.research_area = ""
            st.session_state.discovered_gaps = []
            st.session_state.selected_gap = None
            save_session_data(st.session_state.email, "", "", [], None)
            go_to("topic")

    st.divider()
    with st.expander("Show research brief"):
        st.markdown(result["brief"])
    with st.expander("Show first draft"):
        st.markdown(result["draft"])
    with st.expander("Show critic's feedback"):
        st.markdown(result["critique"])
