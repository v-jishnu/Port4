EVAL_CASES = [
    # order_issue
    {"text": "My package was supposed to arrive last Tuesday but tracking hasn't updated since it left the warehouse.",
     "expected_category": "order_issue", "expected_priority": "medium", "expected_team": "fulfilment"},
    {"text": "I opened the box and it's a completely different item than what I ordered.",
     "expected_category": "order_issue", "expected_priority": "high", "expected_team": "fulfilment"},

    # billing_and_payment
    {"text": "I was billed twice for the same order this month, please refund the duplicate charge.",
     "expected_category": "billing_and_payment", "expected_priority": "high", "expected_team": "billing"},
    {"text": "My invoice for last month's subscription shows an amount higher than what I signed up for.",
     "expected_category": "billing_and_payment", "expected_priority": "medium", "expected_team": "billing"},

    # product_inquiry
    {"text": "Does the Aria wool jacket run true to size or should I size up?",
     "expected_category": "product_inquiry", "expected_priority": "low", "expected_team": "sales"},
    {"text": "Do you ship the Breville Barista espresso machine to Canada?",
     "expected_category": "product_inquiry", "expected_priority": "low", "expected_team": "sales"},

    # technical_support
    {"text": "The mobile app freezes every time I try to update my payment method in settings.",
     "expected_category": "technical_support", "expected_priority": "high", "expected_team": "technical_support"},
    {"text": "My smart watch won't pair with the app anymore after the last update.",
     "expected_category": "technical_support", "expected_priority": "medium", "expected_team": "technical_support"},

    # boundary rules from the system prompt, tested explicitly
    {"text": "The blender I received arrived completely smashed, glass everywhere, I want a replacement.",
     "expected_category": "order_issue", "expected_priority": "high", "expected_team": "fulfilment",
     "note": "boundary rule 1: damaged-in-transit is order_issue even though customer wants a replacement"},
    {"text": "The toaster arrived in perfect condition but it won't heat up at all.",
     "expected_category": "technical_support", "expected_priority": "medium", "expected_team": "technical_support",
     "note": "boundary rule 2: intact but broken is technical_support, not order_issue"},
    {"text": "I was charged twice for my order last week, can you fix the duplicate charge?",
     "expected_category": "billing_and_payment", "expected_priority": "high", "expected_team": "billing",
     "note": "boundary rule 3a: payment dispute on an existing order is billing_and_payment"},
    {"text": "Do you accept Afterpay for purchases?",
     "expected_category": "product_inquiry", "expected_priority": "low", "expected_team": "sales",
     "note": "boundary rule 3b: payment method question with no existing order is product_inquiry"},

    # multi-issue ticket
    {"text": "I still haven't gotten my refund from last month and now the checkout page keeps freezing when I try to place a new order.",
     "expected_category": "billing_and_payment", "expected_priority": "high", "expected_team": "billing",
     "note": "multi-issue: refund (financial loss, higher priority) should win over the checkout bug"},

    # guard rejection cases - never reach the router at all
    {"text": "", "expect_rejection": True, "note": "empty ticket, manual guard"},
    {"text": "asdkjhaskjdh aksjdh laksjdh", "expect_rejection": True, "note": "gibberish, LLM guard"},

    # too vague to be actionable - correctly the guard's job to reject, not the router's
    {"text": "something's wrong with my stuff", "expect_rejection": True,
     "note": "vague enough that the guard should reject it, per its own 'too vague' criterion"},
]
