---
title: "8 Claude Loops to Build 10x Faster"
source: "https://www.youtube.com/watch?v=HGCHgD4uGgY"
author:
  - "[[Austin Marchese]]"
published: 2026-07-04
created: 2026-07-05
description: "Try Nexos Risk-Free for 14 days - https://nexos.ai/austinIn this video I break down the 8 Claude loops I actually use to build 10x faster. Loop Engineering has gone viral, but what are claude loops"
tags:
  - "clippings"
---
![](https://www.youtube.com/watch?v=HGCHgD4uGgY)

Try Nexos Risk-Free for 14 days - https://nexos.ai/austin  
  
In this video I break down the 8 Claude loops I actually use to build 10x faster. Loop Engineering has gone viral, but what are claude loops you can build today that will make a difference. These are broken down into Three buckets, INGEST, BUILD, and COMPOUND, plus one North Star Loop that keeps the whole stack pointed at what actually matters.  
  
Timestamps:  
(0:00) - Loop 1: Data-Ingest Loop  
(1:49) - Loop 2: External AlphaFarming Loop  
(5:03) - Loop 3: Internal AlphaFarming Loop  
(7:11) - Loop 4: Optimization Loop  
(9:11) - Loop 5: Code-Build Loop  
(11:04) - Loop 6: Improve-System Loop  
(13:05) - Loop 7: Ecosystem Monitoring Loop  
(15:42) - Loop 8: North Star Loop  
  
What to watch next ⤵️  
\- Loop engineering foundation: https://www.youtube.com/watch?v=YAS4ojuhbW4  
\- Self-improving system deep dive: https://www.youtube.com/watch?v=2fc0NX9vIJ8  
\- Stop prompting, start agentic engineering: https://www.youtube.com/watch?v=7zZy1QTvokM  
  
\--------  
FOR INDIVIDUALS:  
\- Free 5-day AI playbook (what I used to build a $25M+ startup): https://the-ai-playbook.com/8loops  
\- Use BuildPartner to build 10x faster with Claude Code (try free): https://buildpartner.ai/8loops  
  
FOR BUSINESSES, Ways to work with me:  
\- Apply for my Executive AI Coaching Program: https://www.theincubator.xyz/apply/8loops  
\- Want to build a SaaS product without hiring a CTO? https://www.theincubator.xyz/eng/8loops  
\--------  
  
LINKS MENTIONED IN THIS VIDEO:  
\- Firecrawl (MCP plugin for web scraping): https://firecrawl.link/austin-marchese  
  
If you're new here, I'm Austin Marchese. How I got here...  
16: First business (SAT Math Tutor)  
22: Graduated Stevens Tech, 4.0, College Basketball, software engineering job at JPM  
23: Bitcoin ATM company + building algorithms for a professional gambler (fun story)  
24: Started creating content, grew 100k+ followers, built first agency, The Incubator  
25: Scaled agency to 15+ team members, $75K/M while working full time  
26: Quit my job, joined a startup called IYK  
27: Became COO of a $25M+ tech startup, worked with Ed Sheeran, Chance the Rapper and more  
28: Built a $20M+ real estate portfolio in the background  
29: Transitioned from IYK, re-launched The Incubator, grew it to a 6-figure biz in 30 days. Now building BuildPartner.ai  
  
To everyone who's spending time learning and putting the work in, cheers. Anyone can make comments from the sidelines but not everyone can build...  
  
\- Austin  
  
Follow/Subscribe  
  
\- Instagram: https://www.instagram.com/austin.marchese/  
\- Youtube: https://www.youtube.com/@austin.marchese

## Transcript

### Loop 1: Data-Ingest Loop

**0:00** · Loop number one is a data ingestion loop. Before we cover how to create this loop and why it's so valuable, what is an actual Claude loop? A loop is something that runs continuously or on a specific schedule until a task is complete. And to see it in action, loop one is the data ingestion loop. With AI, at the end of the day, your data is your moat. And if you want to differentiate yourself and get a better output, you have to take data aggregation and ingestion very seriously. To set this up, we first connect our data sources.

**0:24** · If you click the plus in the desktop app and then select connectors, you can then select the specific resources that you interact with. For me, it's Slack, Gmail, and then Granola for call transcripts. Once you establish those connections, it's time to actually create a skill that aggregates the data for you, validates that it's not just contextual noise, and then ingests it into the system. On screen, you can see a prompt that I used to create a skill called a data ingestion loop. This loop will go to Slack for messages, Gmail for emails, Granola for call transcripts, read the last 24 hours, and remove all of the fluff, and only store the valuable information.

**0:53** · For every loop we create, I'm going through a process called skill-driven loop creation, where every loop we create starts as a skill first that we manually run, confirm it works, and then we create a process to automatically run it. At this point, let's assume that we've tested it, and it's now time to actually make this automated. To do this, I use local routines, which I get to by clicking routines, plus, local routine, and then I fill in the information where the instructions is I just use the skill that I already created. In this case, I set the skill to run Mondays at 8:00 a.m.

**1:24** · And for every loop we cover here, you can just create a routine if you want to run it automatically in the background. Now, that's just the first of eight Claude code loops that we'll go through in today's video that will help you build faster and more efficiently.

**1:34** · And for all eight of these loops, I bucket them into three groups. The first is loops that help you ingest data, get better outputs. The next are loops that help you build faster, and the last is a series of loops that help you create a system that automatically improves over time. Loop number two is external alpha farming. So, what is an alpha farming loop? This is a loop that goes, looks for information that's valuable, and then pulls it into your system. And by sourcing the right information, you're able to get better outputs. Now, there are three parts of this loop, and so here's a prompt to create it, but I'm going to go through each step and why it's important.

### Loop 2: External AlphaFarming Loop

**2:04** · The first part of it is you want to establish what alpha you're actually farming. And for this, you want to be very specific. So, if you're a content creator, the alpha could be storytelling patterns or recent news topics. If you're building a product, it could be about conversion funnel benchmarks and optimization tactics. If you're a sales rep, it could be objection handling patterns from reps who are closing your exact customer. The second part of this is identify the sources of alpha. This is where you could use AI to help you create a list of options, but ultimately, this is where your human taste comes in.

**2:32** · The question you have to ask yourself is who online is creating valuable insight about the topics that you're working on.

**2:38** · So, YouTube creators, newsletter creators, Reddit forums, where is there valuable information online that can produce a consistent stream of up-to-date information? The third part is that you validate the source has level two analysis. Most people skip this part, but this is where it becomes an actual loop. So, level one analysis is where AI just gives you basic stuff, right? The basic framework, something that doesn't really differentiate the output. Level two analysis is the non-obvious information that brings an output from good to great. And you want to curate it so only level two information is ingested into your system.

**3:08** · Here on screen, you can see me running the alpha farming loop, and you can see that it's actually going and fetching different resources. One thing I want to call out is that I do use an MCP called Firecall that helps me get better information across the internet.

**3:20** · Now, before we get to the next loop, which will focus on internal alpha farming, you may find that a lot of what we're covering feels a bit technical, which brings us to today's video sponsor, nexus.ai. This is what I call an AI platform, which is a category of tools I love. And then the reason for this is that it removes all the technical skills that are normally needed to set up AI agent systems, and it can save you hundreds of dollars each month because you don't have to pay for five different AI tools. There are three specific features that I love. The first is that every flagship model is included in a single nexus login.

**3:47** · So, ChatGPT, Claude, Gemini, Grok, 200 plus other models can all be accessed directly through Nexus. And this is critical because there's really no single best AI model. Different ones are better at different things, and Nexus AI will automatically route each prompt to the best one. The second feature is that there's zero data retention. This means that your data is never used to train their models, and that alone is one of the big reasons why I can even consider using this tool for client work. And the third feature is their no-code AI agent builder. At the end of the day, if you can use the internet, you can use Nexus to build AI agents.

**4:18** · You just describe what you want, and Nexus will build the agent for you. And whether it's for one-time jobs like I need to do deep research on this topic like right now, or for repetitive tasks like turning your notes into a weekly report automatically, Nexus will handle all of this. For me, I have a lot of products in my ecosystem, my YouTube, my newsletter, Build Partner, so it's hard to keep track of all of this. So, what I can do is create a weekly report that analyzes my entire marketing funnel, and connect it to my Slack to send my entire team a summary of website visits, conversions, and what we need to work on. This is a task that I'd normally just never do because I just don't have the time.

**4:49** · So, to check out Nexus, click the first link in the description you'll get 50% off. And that 50% discount is for a limited time because when I was working with them, I had to stress the importance of getting a large discount for everyone watching. So, go check that out. Now, getting to loop number three, which is internal alpha farming loop. If loop number two was all about hunting for external alpha farming, loop number three hunts for internal alpha. This will look across all the data that's already in your system, and surface what's recurring, where the gaps are, and what you should be doing about it.

### Loop 3: Internal AlphaFarming Loop

**5:17** · To set this up, it's broken down into three parts. The first part is you want to establish what internal alpha you're farming. If you're a content creator, which video concepts actually landed and performed? If you're building a product, what features do people keep requesting?

**5:29** · If you're a sales rep, what questions or rebuttals does everyone have, and should you build that into the service? This is the exact kind of pattern that humans will miss, but a loop doesn't. And the insights from this can lead to changes that actually move the needle. The second part is that you want to point it at the right data sets. In loop number one, we set up data ingestion, so this builds on exactly this. But now, you actually have to ask, do I have the necessary data for internal alpha farming loop to actually work? And if the answer is no, this identifies gaps in your data pipeline, and you have to resolve that. And part three is the output is an action list, not a report.

**6:03** · Essentially, every internal dashboard tells you all the information about what happened, but none of them actually tell you what to do about it. And one of the things that I tell my team is, don't bring me a problem, bring me a solution.

**6:13** · And that's exactly what this loop is designed to do. It creates an implementation plan that passes our plan verification skill to make sure it hits our requirements for any sort of delivery plan. To create this loop, first we need to create that {slash} plan verification skill, which is a utility skill that we'll use whenever we want to verify a plan. Here's a prompt actually create that skill, which will interview you about what tools you're currently using and what you're open to and not open to implementing. The key here is that any implementation plan that this creates has to actually be a viable option.

**6:42** · So, the skill is used to keep AI honest about any plan that it actually proposes. Then you use this prompt to create an internal alpha farming loop skill, which will create the loop, identify recurring patterns, and suggest places to improve. This loop will help you identify what you have to build next based on the data you're ingesting. As this loop runs, it'll look at the data that you're ingesting and suggest places for improvement. Now, we've covered ways to ingest data and how to actually analyze it, but the next three loops are all about improving the process in which you build. Loop number four is an optimization loop.

### Loop 4: Optimization Loop

**7:11** · This is a process of optimizing a system to approach a specific metric or quantifiable result. For example, it does something pass level two analysis, right? That's hard to actually quantify.

**7:23** · But what a proper optimization loop does is it looks at something that is an objective metric. An example could be, how quickly does a website load? So, what this loop will do is it'll pick a specific goal, it'll run a loop, measure the result, if it doesn't actually fit the goal, it'll propose a solution, it'll apply it, re-measure it, and continue this loop until it gets to that final goal. On screen, you'll see a bunch of areas where an optimization loop makes sense, which is typically for more technical delivery mechanisms because these are super quantifiable.

**7:52** · When I first started thinking about loops, I thought that all of the feedback back and forth had to happen almost instantly. Make a change, measure result, etc. But that doesn't necessarily have to be the case. So, for example, let's say you have a website and you want to try and optimize conversion rate. You could have a loop that runs, checks the conversion rate for day one, makes a tweak, checks it for day two, etc. And where this feedback loop is over a course of 24 hours. This is entirely fine, and once I kind of realized this, this opened up my brain to the realm of possibilities because initially I thought that this feedback mechanism was way too slow.

**8:24** · Now, to create an optimization loop, here is a templated prompt that you can use, and you can fill in for whatever you're trying to work on. Now, before I get to the next loop, if this is your first video of mine, welcome to channel, but if this is your second or more, here is our anti-slop agreement. All of the stuff that I do in this video, right?

**8:39** · The the visual, the design, the hours of research, this is for humans, not for AI robots. That's part of the reason why I put all these prompts on screen because it's easier for you to read and screenshot, and it's not for these AI robots to see. So, as part of the agreement, all I ask is that you subscribe to this channel to help this content reach more people. Also, every video I give away a Claude Mac subscription, and this video's winner is the goat I'm Jasmine. They're building a platform to help people connect faster.

**9:04** · Absolute bangers. To enter the giveaway, comment below with what you're building, and if you already entered, you can enter again by providing an update on whatever you're working on. Bring us to loop number five, which is code build loop. This loop is specifically if you want to vibe code a product, and everyone watching this video should be vibe coding whether you have a technical background or not. And the key with anything vibe coding is you don't want to just go and grip and rip things. You need to plan before you actually do anything. And what this loop will do is your goals will get extracted. It verifies a delivery plan, and then, and only then, does it go through a loop to complete the tasks.

### Loop 5: Code-Build Loop

**9:33** · On screen, you can see the prompt, which breaks the task into six parts, which leverages skill chaining to create the actual loop.

**9:41** · First, it'll extract or bring in the goal. So, this can be through an interview, or you can bring in a document you already have. The second is it'll plan the delivery using Claude's built-in plan mode. The third is sign off on the plan. This is where you, the human, comes in. The fourth is it'll build it. Fifth is it'll review the code. This uses Claude's /code-review--fix.

**9:59** · Sixth, it'll verify the behavior matches the goal. It'll use Claude's /verify to help with this. Now, I went through all six features pretty quickly there, but there are two specific concepts that are critical you understand as you take these loops and start creating your own from scratch. The first is that there's an approval gate. If you look at the third step, it says sign off on the plan. That's an approval gate. And we do this at this stage because this is what I call a critical call checkpoint. If at this point you're in the wrong direction, steps four, five, and six are just going to be entirely wrong, and you're wasting time and money.

**10:26** · A general rule of thumb I have is that for any loop that you create, if there is any critical call checkpoint, then you need to add a human approval gate. Now, to be clear, some of these loops may have none of these, but others may have four or five. It really depends on what you're building. The second thing is dynamic workflows. This is how Anthropic divides the goal you have amongst AI agents to complete the task. This is how it actually goes and builds whatever you're trying to build. And there are six patterns that Anthropic has documented for these dynamic workflows, which you can see all of them on screen.

**10:54** · But to 80/20 this whole thing, you don't actually have to worry about which one.

**10:59** · It'll figure it out for you. But if you do want to play around with it, you can look at the screenshot as a good starting point. Okay, so we've gone through data ingestion as well as how you can build quickly. But loop number six is about creating a system that self-improves with the improve system loop. Of the eight loops that we're covering, this is by far my favorite because it single-handedly transformed my business. Twice a week, I run an improve system loop, Tuesday end of day and Friday end of day, and that makes it so that my entire AI system is self-improving. There are two layers to actually get this done. The first layer is you have to build the improve system skill.

### Loop 6: Improve-System Loop

**11:29** · This is what actually looks at your system and figures out ways to improve it. So, it'll read sessions, it'll find patterns, it'll propose changes, and I've spoken about this a lot on my channel, but if you want to use the exact one I use, I do have a plugin called billpartner.ai, and you can do /bp improve system, and that's exactly what I use. Here on my screen, you can see me running this skill manually on my system, and it shows all the ways that I can currently improve it. Now that I look at it, I will have to do after filming this video. Now, the second layer for this loop is to actually create the loop, and this is wrapping the skill in a self-improving system loop.

**11:58** · But, within this prompt, I log every change that it makes to a changelog.md file. The reason is I want to see what is actually happening in my system, and within those changes, it actually buckets it into three categories. The first bucket is auto-approve. These are all of the low-risk things that it can just automatically improve, aren't really up for debate to improve the system. This is like the self-improving component.

**12:20** · Bucket two is need sign-off. These are higher-stakes stuff, like skill edits, or new skill candidates, or structural changes. This is anything where the wrong choice could actually degrade output quality. These changes get written to a review file as a checkbox list. For each of the suggestions, you can improve, reject, or approve and don't ask me again. This is a way to tweak the system over time. And the third bucket is more context needed.

**12:41** · This is stuff that the loop can't decide on its own. Let's say, for example, you mention someone three times, and it can't tell if this is a new client or a one-off relationship. This will go in that same review file from bucket two.

**12:51** · This three-bucket system is what I found is an effective middle ground to make an automated system that improves without you, makes it easy for you to label improvements, and also keeps you as the tastemaker, so that your system doesn't slowly degrade in quality from what you actually want it to produce. Loop number seven is ecosystem monitoring loop.

### Loop 7: Ecosystem Monitoring Loop

**13:08** · Whenever you create a loop, more operational debt is added to your system, and this ecosystem monitoring loop is the loop that manages your other loops. This is some loop-ception type sh Now, before you say this is ridiculous, we're just going to be burning through tokens, there's some key features why this can actually save you tokens while running a more efficient system. On screen, you'll see a prompt to create the actual loop, but there are three important features to call out. The first feature is it surfaces composability opportunities across loops. As you build more loops, you'll unknowingly write the same logic twice.

**13:38** · For example, let's say you have two loops that require fetching data from Slack. There's a chance that both of these contain the same logic. The so the ecosystem monitoring loop scans your loop library, finds repeated logic, and suggests pulling it out into a composable skill that every loop can call. That's exactly what we did with the plan verification skill back in loop number three. We built it once and then any other loop can use it. The more loops you create and the more logic that's shared between them, the more likely you're going to fall into a whack-a-mole trap. This is where you'll see a problem in one skill, you'll fix it, and then it'll pop up in another place.

**14:08** · If the logics were used across skills, you want to abstract that into a single skill that gets called by the other loops. And to all the programmers out there, yes, it's like you're creating a reusable function. Feature number two is the health check across the stack. You can cross-reference every loop's output to see what's running successfully. But for this to work, every loop has to log its results properly. So we'll create a write run log utility skill that writes everything to this folder. On screen you can see a prompt that will create the specific skill and simultaneously enhance any existing loops that you have.

**14:37** · We do this so that every loop writes to the same location. And if you update this specific write log skill, it'll update across every other loop that you have running. And by having an effective way to monitor loops, you're going to keep a close eye on everything that's running, and you'll quickly notice what is and isn't working. And as a result, you'll be able to turn off what isn't working, saving you tokens. I can guarantee there are probably millions of people right now running loops that don't know it, and they're just burning tokens. This helps you avoid that. And the third feature is it dynamically updates, which removes operational debt.

**15:06** · Every loop that we've created in this video has the same naming convention. It's name-loop.

**15:12** · And on each run of this ecosystem monitoring loop, it scans the skills for any skill that has this name. And as a result, this ecosystem monitoring loop will automatically include any additional loops that you start running.

**15:24** · This means that there's no operational debt to actually maintain this monitoring loop because it self-corrects. And remember, for every loop that I'm covering this video, if you want to run them continuously or on a schedule, you can run routines directly through Claude Desktop app.

**15:37** · Now, the past seven loops that I covered are game-changers for productivity, but this last one could make the biggest difference. Loop number eight is your North Star loop. If the other seven loops are instruments, this loop is the compass. This loop will monitor your activity and make sure you're actually pushing towards your goals. Simply put, this is asking, is everything that I'm doing pointed at my actual goal? And there are four parts to this loop, and you can see the prompt on screen. Part one is you lock in the North Star. This is similar to the goal extraction we did earlier, but you have to establish like what are your actual goals?

### Loop 8: North Star Loop

**16:03** · Hit 100k subs, land 12 new clients, ship four paid products, get a promotion, sign four new clients. Like what are these goals that you want to be pushing towards? Part two is it'll analyze your trajectory. This will read your Claude session history, the data you're ingesting, the loop results, everything that you've been working on, and see where you're going. Part three is it summarizes it. This is about forward extrapolation. Essentially saying, if nothing changes, here's where you're going to land. For me, this is usually the biggest kick in the ass because it's like, if I don't change anything, then I'm going to be here in six months.

**16:32** · The fourth part is proposed direction changes. If drift is detected, it'll surface what's pulling you in that direction. It'll detect this drift and then propose things that you should change instead. This is the type of loop that frankly everybody needs to start using. So, those are the eight loops that you need to build bucketed into three different groups. Loops that help you ingest data, build faster, and create a system that compounds and can be maintained over time. Now, if you like this video, you'll love this video where I dive deep into how you can set up Claude to be a self-improving system.

**17:01** · It builds on a lot of the topics I covered here. And if you pair what I cover in that video with the loops that I walked through today, you're going to be on a whole 'nother level. So, go check that video out, and I'll see you over there. Peace.