# Smart AI Agent - User Guide

This guide explains how to enable, configure, and monitor the Smart AI Agent features in your autodialer system. The AI Agent can autonomously handle outbound calls, interact with leads using natural language, and automatically categorize outcomes.

## 1. Enabling AI for a Campaign

To use the AI Agent, you must first enable it within a specific campaign:

1. Navigate to **Campaigns > Create Campaign** (or edit an existing one).
2. Follow the standard setup steps for Basic Information and Dialing Methods.
3. Under **Call Rules & Compliance**, you will find the **Enable AI Agent** toggle (if available in your setup) or you can enable it from the Campaign detail page by clicking the **AI Configuration** button.
4. Ensure your campaign is set up with an **Outbound Carrier** and **Trunks** configured to reach your leads.

## 2. Configuring the AI Agent Persona

Once a campaign is created, you must configure the AI's behavior and personality:

1. Go to the **Campaigns** list and select your campaign.
2. Click the **AI Configuration** (Robot icon) button in the top action bar to open the AI settings.
3. Fill out the AI Configuration form:
   - **Agent Persona**: Describe the AI's role (e.g., "You are a friendly sales associate for ACME Corp. Keep sentences short and energetic.").
   - **System Prompt / Objective**: Define the exact goal of the call (e.g., "Qualify the lead by asking if they are interested in solar energy. If yes, transfer them to a human agent.").
   - **Voice Configuration**: Select the preferred voice setting (e.g., sarvam-1, amrit, etc.) if your system provides voice options.
   - **Transfer & Disposition Settings**: Tell the AI under what conditions to transfer a call to a human agent, and what disposition codes to apply for specific outcomes.
4. Save the configuration. Active AI campaigns will now intercept outgoing calls and route them to the generative AI worker.

## 3. Testing the AI Agent

Before launching a live campaign to thousands of leads, you should test the AI's responses and latency:

1. From the **AI Configuration** page, look for the **Test AI Agent** or **Simulate Call** section.
2. Enter a valid test phone number.
3. Click **Initiate Test Call**.
4. Your phone will ring. Answer it and interact with the AI to ensure the persona and latency meet your expectations.

## 4. Monitoring AI Calls and Transcripts

The system automatically logs all AI interactions, including full conversation transcripts and AI-determined call outcomes.

1. Navigate to the **Campaign Detail** page.
2. Click on **AI Call Logs** or check the **Call Logs** tab and filter by "AI Handled".
3. For each call, you will see metrics like call duration, AI latency, and the final disposition chosen by the AI.
4. Click **View Transcript** on any specific call to see a turn-by-turn dialogue between the AI and the Lead. This is crucial for refining your Agent Persona over time.

## 5. Best Practices
* **Keep Prompts Concise**: Long prompts increase processing time. Give the AI clear, step-by-step instructions.
* **Test Thoroughly**: Always run at least 3-5 test calls to verify edge cases (e.g., hanging up early, asking for a human, asking unrelated questions).
* **Monitor Transcripts**: In the first few hours of a campaign, actively read the transcripts to see if the AI is hallucinating or getting stuck. Adjust the Persona accordingly.
