# Clerk

Clerk helps you decide whether to buy a product this week, in your city, before you spend the money.

You type three things:

- the product, such as Sony WH-1000XM5
- the city, such as Hyderabad, Telangana, India
- a budget in rupees, if you have one

Clerk then looks up live prices, nearby shops, news, and reviews. It comes back with one answer: **Buy**, **Hold**, or **See it**. Each reason has a link you can open. Clerk does not invent a price it did not find.

This project is for the [SerpApi India Hackathon 2026](https://serpapi.github.io/serpapi-india-hackathon-2026/), on the AI Agents track. The live lookups come from SerpApi. Without those lookups, Clerk has nothing to decide.

## What the answers mean

**Buy** means the India price is inside your budget, the listings agree, and the news did not turn up a recall or a newer model.

**Hold** means wait. A headline may mention a recall, a newer model, or a price that is still above your budget.

**See it** means go look in person, or check one more source. The prices may be far apart, or there may not be enough evidence to spend the money.

## How it works

Clerk works like a small desk. The helpers go in order, and you can watch each one on the page.

1. **Planner** writes the searches before any lookup is spent.
2. **Market** checks who is selling the product and at what price. Cases, skins, and other add-ons are set aside so a cheap case is not treated as the product.
3. **Street** looks for a shop in your city where you could see it.
4. **Wire** reads the news for recalls, new models, and sales.
5. **Record** finds reviews and other pages you can read before you pay.
6. **Second** runs only when those results disagree. A sale priced in dollars, next to an India price in rupees, makes Second check whether a newer model is already out. If Market found no India price, Second searches the shops again with a tighter query. If the results already agree, Second does nothing.
7. **Critic** can block a buy when too little came back, or when the extra search fails.
8. **Clerk** writes the slip: the answer, up to three reasons, and one next step with a link.

A normal question uses 4 SerpApi searches. A question that needs Second uses 5.

A dollar sale is not treated as the India price. A headline about a different model, such as an older one, is not treated as a reason to wait. A newer model in the same family, such as XM6 after XM5, is.

## Try it

Open the page and choose **Headphones in Hyderabad**. That example asks about the Sony WH-1000XM5 with a budget of ₹25,000.

On a recent run, Market kept the headphones from ₹19,000 and set aside a case and skins. The news was full of US sale prices near $200. Second then found headlines about the newer WH-1000XM6, so the answer was **Hold**.

## Run it on your computer

You need Python 3.10 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Open `.env` and put your own SerpApi key on this line:

```
SERPAPI_API_KEY=your-key-here
```

Keep that file on your computer. It is not part of this repository.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

To check the decision rules without spending searches:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## For the hackathon

- Track: AI Agents
- SerpApi tools: shopping, maps, news, and web search, aimed at India
- Show the page running on your own computer in a screen recording under three minutes
- Say which AI tools you used. This project was built with help from Cursor
