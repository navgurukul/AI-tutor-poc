# Groundedness run — long-q-v1

2026-09-23T05:13:51+00:00 · tutor `qwen2.5:1.5b` · http://127.0.0.1:8756 · budget backend default · judge gemma3:4b (local, via Ollama)

Gold set `docs/groundedness/evalset-long.json` over *General Science (Class 6), MSCERT + NCERT Class 6 Science*. Each answer is graded against the excerpt block that turn actually read, not against the pages it cited.

## Headline

| | |
|---|---|
| Groundedness (claims) | **78%** (57/73 claims supported) |
| Groundedness (per turn) | 79% |
| Contradictions | **3** claims, in 3 of 11 turns |
| Unsupported | 13 claims |
| Key coverage | 47% |
| Context recall | 33% of gold passages reached the prompt |
| Fully grounded turns | 3/11 |
| Supported on a quote not in the excerpt | 3 — judge slips, check by hand |
| Off-syllabus abstention | held |

| outcome | turns |
|---|---|
| grounded and complete | 4 |
| contradicts the book | 3 |
| grounded but thin | 2 |
| ungrounded and incomplete | 2 |
| abstained | 1 |

## The judge, graded first

8/14 known verdicts correct. It missed real support 0% of the time and waved a false claim through 12% of the time — the error bars on every number above.

| statement | expected | judge said |
|---|---|---|
| Decantation is the name for the heavier part of the mixture settling at the bottom of the vessel. | contradicted | supported |
| A fish can survive out of water for several hours by using its swim bladder. | unsupported | contradicted |
| Two north poles brought close to each other pull towards each other. | contradicted | unsupported |
| In an electric circuit the current is taken to flow from the negative terminal to the positive terminal of the cell. | contradicted | unsupported |
| The fulcrum of a lever is the weight that the lever lifts. | contradicted | unsupported |
| The steeper the inclined plane, the less weight we have to bear. | contradicted | unsupported |

## Per item

| item | grounded | key | recall | claims | outcome |
|---|---|---|---|---|---|
| `L1-clean-rice` | 100% | 67% | 50% | 8 | grounded and complete |
| `L2-tea-pan-lid` | 100% | 75% | 50% | 7 | grounded and complete |
| `L3-fish-and-camel` | 67% | 25% | 50% | 6 | ungrounded and incomplete |
| `L4-two-bar-magnets` | 60% | 0% | 0% | 5 | contradicts the book |
| `L5-bulb-did-not-glow` | 83% | 25% | 67% | 6 | grounded but thin |
| `L6-where-rain-comes-from` | 83% | 100% | 33% | 6 | grounded and complete |
| `L7-only-rice-and-chapati` | 100% | 33% | 33% | 5 | grounded but thin |
| `L8-crowbar-three-parts` | 43% | 60% | 0% | 7 | contradicts the book |
| `L9-drum-up-the-plank` | 80% | 50% | 33% | 5 | grounded and complete |
| `L10-bicycle-wheel` | 83% | 50% | 50% | 6 | contradicts the book |
| `L11-off-syllabus-metro` | 0% | — | — | 3 | abstained |
| `L12-concrete-colony` | 67% | 33% | 0% | 12 | ungrounded and incomplete |

---

### `L1-clean-rice` — Yesterday my mother bought a packet of rice from the shop and it had small pieces of stone in it, and some dust also came out when she washed it. Can you tell me which two different methods we should use to make that rice clean before cooking, and explain how each of those methods actually works?

**Retrieved:** 2 · **read:** 1 passage(s), 644 chars · **gold pages:** p.36, p.38 · **cited:** p.38

**Gold passage reached the prompt:** 1/2 quotes

**Answer**

> Certainly! When washing rice, you can use either the sedimentation method or the decantation method to clean it. 
> 
> Firstly, the sedimentation method involves adding water to the rice and letting it sit. The heavier grains of rice will sink to the bottom, while the lighter dust particles will float on the surface. By tilting the vessel, you can easily pour off the dirty water, leaving behind the clean rice. This method works because the heavier grains of rice settle at the bottom, while the lighter dust particles remain in the water.
> 
> Alternatively, the decantation method involves pouring the water off the rice, leaving the clean grains behind. This method works because the water with the dust particles is poured off, while the clean rice remains in the vessel. Both methods effectively remove the impurities from the rice, ensuring it is clean and ready for cooking.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| When washing rice, you can use either the sedimentation method or the decantation method to clean it. | supported | When the heavier component in a mixture settles after water is added to it, the process is called sedimentation. When the water (along with the dust) is removed, the process is cal |
| Firstly, the sedimentation method involves adding water to the rice and letting it sit. | supported | When the heavier component in a mixture settles after water is added to it, the process is called sedimentation. |
| The heavier grains of rice will sink to the bottom, while the lighter dust particles will float on the surface. | supported | When the heavier component in a mixture settles after water is added to it, the process is called sedimentation. |
| By tilting the vessel, you can easily pour off the dirty water, leaving behind the clean rice. | supported | When the vessel is tilted to pour out the dirty water? |
| This method works because the heavier grains of rice settle at the bottom, while the lighter dust particles remain in the water. | supported | When the heavier component in a mixture settles after water is added to it, the process is called sedimentation. |
| Alternatively, the decantation method involves pouring the water off the rice, leaving the clean grains behind. | supported | When the water (along with the dust) is removed, the process is called decantation (Fig. 5.8). |
| This method works because the water with the dust particles is poured off, while the clean rice remains in the vessel. | supported | When the water (along with the dust) is removed, the process is called decantation (Fig. 5.8). |
| Both methods effectively remove the impurities from the rice, ensuring it is clean and ready for cooking. | supported | When the heavier component in a mixture settles after water is added to it, the process is called sedimentation. When the water (along with the dust) is removed, the process is cal |

**What the book answers with:** ✗ the stones are removed by handpicking · ✓ adding water lets the heavier part settle -- sedimentation · ✓ pouring off the dirty water is decantation

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - METHODS OF SEPARATION - pp. 38-39
Rice or pulses are usually washed before cooking. When you add water to these, the impurities like dust particles You may have also noticed similar sieves being used at construction sites get separated. These impurities go into water. Now, what will sink to the bottom of the vessel - rice or dust? Why? Have you seen that the vessel is tilted to pour out the dirty water? When the heavier component in a mixture settles after water is added to it, the process is called sedimentation. When the water (along with the dust) is removed, the process is called decantation (Fig. 5.8). …
```
</details>

---

### `L2-tea-pan-lid` — When my mother boils water in a pan for tea, the water slowly becomes less and less, and after some time I can see many small drops of water sitting under the lid. Can you tell me the names of these two processes and explain what is happening to the water in each of them?

**Retrieved:** 2 · **read:** 1 passage(s), 655 chars · **gold pages:** p.40, p.41 · **cited:** p.34, p.41

**Gold passage reached the prompt:** 1/2 quotes

**Answer**

> When your mother boils water in a pan for tea, two processes are happening: evaporation and condensation. 
> 
> First, as the water heats up, it turns into steam. This steam rises and cools as it moves through the air. When it hits the lid of the pot, it cools down and turns back into water, forming the small drops you see. This process is called condensation. 
> 
> The water in the pot is continuously evaporating into the air, and then condensing back into water droplets when it cools down. This cycle continues until all the water has been converted into steam, and then back into water droplets.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| When your mother boils water in a pan for tea, two processes are happening: evaporation and condensation. | supported | When the steam comes in contact with the metal plate cooled with ice, it condenses and forms liquid water. The water drops that you observed falling from the plate, were due to con |
| First, as the water heats up, it turns into steam. | supported | When the steam comes in contact with the metal plate cooled with ice, it condenses and forms liquid water. |
| This steam rises and cools as it moves through the air. | supported | When the steam comes in contact with the metal plate cooled with ice, it condenses and forms liquid water. |
| When it hits the lid of the pot, it cools down and turns back into water, forming the small drops you see. | supported | When the steam comes in contact with the metal plate cooled with ice, it condenses and forms liquid water. The water drops that you observed falling from the plate, were due to con |
| This process is called condensation. | supported | The process of conversion of water vapour into its liquid form is called condensation. |
| The water in the pot is continuously evaporating into the air, and then condensing back into water droplets when it cools down. | supported | When the steam comes in contact with the metal plate cooled with ice, it condenses and forms liquid water. The water drops that you observed falling from the plate, were due to con |
| This cycle continues until all the water has been converted into steam, and then back into water droplets. | supported | When the steam comes in contact with the metal plate cooled with ice, it condenses and forms liquid water. The water drops that you observed falling from the plate, were due to con |

**What the book answers with:** ✓ the water leaving the pan is evaporation · ✗ evaporation is water turning into its vapour · ✓ the drops under the lid are condensation · ✓ condensation is vapour turning back into liquid water

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - METHODS OF SEPARATION - p. 41
Take a metal plate with some ice on it. Hold the plate just above the spout of the kettle as shown in Fig. 5.13. What do you observe? Let all the water in the kettle boil off.

When the steam comes in contact with the metal plate cooled with ice, it condenses and forms liquid water. The water drops that you observed falling from the plate, were due to condensation of steam. The process of conversion of water vapour into its liquid form is called condensation.

Did you ever see water drops condensed under a plate that has been used to cover a vessel containing milk that has just been boiled?
```
</details>

---

### `L3-fish-and-camel` — My teacher told the class that a fish cannot live out of water and that a camel cannot live in the sea. Can you explain what the two words habitat and adaptation mean, and then use both of those words to tell me why each of those animals can only live in its own place?

**Retrieved:** 2 · **read:** 1 passage(s), 590 chars · **gold pages:** p.80 · **cited:** p.81

**Gold passage reached the prompt:** 1/2 quotes

**Answer**

> Certainly! The term "habitat" refers to the environment where an organism naturally lives and thrives. For instance, a fish lives in water, while a camel lives in desert environments. Adaptation, on the other hand, is the process by which an organism changes its characteristics to better suit its environment. A fish has adapted to live in water by having gills for breathing underwater and a streamlined body for efficient swimming. Similarly, a camel has adapted to live in deserts by having thick fur to protect it from the sun and heat, and a hump to store fat for water and food during long journeys. Thus, each organism has developed specific adaptations that allow it to survive and thrive in its particular habitat.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| The term "habitat" refers to the environment where an organism naturally lives and thrives. | supported | In all this variety of organisms, we will find that they have certain features that help them live in the surroundings in which they are normally found. |
| For instance, a fish lives in water, while a camel lives in desert environments. | supported | That is why a fish cannot live out of water and a camel cannot live in sea. |
| Adaptation, on the other hand, is the process by which an organism changes its characteristics to better suit its environment. | **unsupported** | Adaptation of organisms differ depending on their place of dwelling. |
| A fish has adapted to live in water by having gills for breathing underwater and a streamlined body for efficient swimming. | **unsupported** | A fish cannot live out of water and a camel cannot live in sea. |
| Similarly, a camel has adapted to live in deserts by having thick fur to protect it from the sun and heat, and a hump to store fat for water and food during long journeys. | supported | The presence of specific features or certain habits, which enable an organism to live naturally in a place is called adaptation. Adaptation of organisms differ depending on their p |
| Thus, each organism has developed specific adaptations that allow it to survive and thrive in its particular habitat. | supported | The presence of specific features or certain habits, which enable an organism to live naturally in a place is called adaptation. Adaptation of organisms differ depending on their p |

**What the book answers with:** ✗ habitat is the place where an organism lives · ✗ the habitat provides food, water, air and shelter · ✓ adaptation is the features or habits that let it live there · ✗ that is why the fish cannot live out of water and the camel cannot live in the sea

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - HABITAT AND ADAPTATION - p. 81
… We have taken only two examples from a very wide variety of animals and plants that live on the Earth. In all this variety of organisms, we will find that they have certain features that help them live in the surroundings in which they are normally found. The presence of specific features or certain habits, which enable an organism to live naturally in a place is called adaptation. Adaptation of organisms differ depending on their place of dwelling. That is why a fish cannot live out of water and a camel cannot live in sea.
```
</details>

---

### `L4-two-bar-magnets` — I keep two bar magnets in my school bag and something strange keeps happening with them. Sometimes when I bring them close they jump towards each other and stick, but if I turn one of them around first, they push each other away instead. What are the two ends of a magnet called, and why do these two different things happen?

**Retrieved:** 2 · **read:** 1 passage(s), 352 chars · **gold pages:** p.107, p.108 · **cited:** p.129

**Gold passage reached the prompt:** 0/2 quotes

**Answer**

> The two ends of a magnet are called poles. These poles are near the ends of the magnet and attract each other. When you bring two magnets close, their poles attract each other, causing them to stick together. However, if you turn one of the magnets around first, it changes the direction of the poles, causing them to push each other away instead. This is because the magnetic poles are attracted to each other, but the magnets' orientation affects how they interact with each other.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| The two ends of a magnet are called poles. | supported | Poles of a magnet are said to be near these ends. |
| These poles are near the ends of the magnet and attract each other. | supported | Poles of a magnet are said to be near these ends. |
| When you bring two magnets close, their poles attract each other, causing them to stick together. | supported | Poles of a magnet are said to be near these ends. |
| However, if you turn one of the magnets around first, it changes the direction of the poles, causing them to push each other away instead. | **CONTRADICTED** | However, if you turn one of the magnets around first, it changes the direction of the poles, causing them to push each other away instead. |
| This is because the magnetic poles are attracted to each other, but the magnets' orientation affects how they interact with each other. | **unsupported** | Poles of a magnet are said to be near these ends. |

**What the book answers with:** ✗ the two ends are the north pole and the south pole · ✗ like poles repel · ✗ opposite poles attract

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - POLES OF MAGNET - p. 129
to two ends of a bar magnet. Poles of a magnet are said to be near these ends. Try and bring a few magnets of different shapes to the classroom. Check for the location of the poles on these magnets using iron filings. Can you now mark the location of poles in the kind of magnets shown in Fig. 13.4?
```
</details>

---

### `L5-bulb-did-not-glow` — I joined a bulb to an electric cell with two wires the way my elder brother showed me, but the bulb did not glow at all. Can you explain to me what an electric circuit really is, in which direction the current is taken to flow inside it, and give me one reason why a bulb may not light up?

**Retrieved:** 2 · **read:** 1 passage(s), 655 chars · **gold pages:** p.119 · **cited:** p.119

**Gold passage reached the prompt:** 2/3 quotes

**Answer**

> Sure, I'd be happy to explain. An electric circuit is a path that allows electricity to flow from one point to another. Inside the circuit, the direction of the current is taken to be from the positive terminal of the electric cell to the negative terminal. When a bulb is connected to an electric cell, the current flows through the wires and the bulb. If there's a break in the path of the current, like a break in the filament of the bulb, the current can't flow, and the bulb won't light up. One reason a bulb might not light up is a break in its filament.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Sure, I'd be happy to explain. | **unsupported** | A break in the filament of an electric bulb means a break in the path of the current between the terminals of the electric cell. |
| An electric circuit is a path that allows electricity to flow from one point to another. | supported | In an electric circuit, the direction of current is taken to be from the positive to the negative terminal of the electric cell as shown in Fig.12.6. |
| Inside the circuit, the direction of the current is taken to be from the positive terminal of the electric cell to the negative terminal. | supported | In an electric circuit, the direction of current is taken to be from the positive to the negative terminal of the electric cell as shown in Fig.12.6. |
| When a bulb is connected to an electric cell, the current flows through the wires and the bulb. | supported | When the An electric bulb may fuse due to many reasons. One reason for a bulb to fuse is a break in its filament. A break in the filament of an electric bulb means a break in the p |
| If there's a break in the path of the current, like a break in the filament of the bulb, the current can't flow, and the bulb won't light up. | supported | A break in the filament of an electric bulb means a break in the path of the current between the terminals of the electric cell. Therefore, a fused bulb does not light up as no cur |
| One reason a bulb might not light up is a break in its filament. | supported | A break in the filament of an electric bulb means a break in the path of the current between the terminals of the electric cell. |

**What the book answers with:** ✗ a circuit is a complete path for the current between the two terminals of the cell · ✗ the bulb glows only when current flows through the circuit · ✗ the current is taken to flow from the positive terminal to the negative terminal · ✓ a break in the filament stops the current, so the bulb does not light

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - AN ELECTRIC CIRCUIT - p. 119
In an electric circuit, the direction of current is taken to be from the positive to the negative terminal of the electric cell as shown in Fig.12.6. When the An electric bulb may fuse due to many reasons. One reason for a bulb to fuse is a break in its filament. A break in the filament of an electric bulb means a break in the path of the current between the terminals of the electric cell. Therefore, a fused bulb does not light up as no current passes through its filament.

Now we know how to make a bulb light up using an electric cell. Would you like to make a torch for yourself? Activity 3
```
</details>

---

### `L6-where-rain-comes-from` — My little sister asked me where rain comes from, and also why the sea does not become empty even though the sun keeps drying up so much of its water every day. Can you explain the whole journey of the water to her, starting from how it goes up into the air and ending with how it comes back to the ocean?

**Retrieved:** 2 · **read:** 1 passage(s), 636 chars · **gold pages:** p.140, p.141 · **cited:** p.139, p.141

**Gold passage reached the prompt:** 1/3 quotes

**Answer**

> Sure, I'd be happy to explain the water cycle to your sister. Water evaporates from oceans, rivers, and lakes when the sun heats it up. This water vapor rises into the air, where it cools and condenses into clouds. When the clouds get heavy, they release water back to the earth as rain, snow, or hail. This water then flows back into the oceans, rivers, and lakes, completing the cycle. This continuous process keeps the water supply on land.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Sure, I'd be happy to explain the water cycle to your sister. | **unsupported** | Thus, water from the ocean and surface of the earth goes into air as vapour; returns as rain, hail or snow and finally goes back to the ocean s. |
| Water evaporates from oceans, rivers, and lakes when the sun heats it up. | supported | Thus, water from the ocean and surface of the earth goes into air as vapour; returns as rain, hail or snow and finally goes back to the ocean s. |
| This water vapor rises into the air, where it cools and condenses into clouds. | supported | Thus, water from the ocean and surface of the earth goes into air as vapour; |
| When the clouds get heavy, they release water back to the earth as rain, snow, or hail. | supported | Thus, water from the ocean and surface of the earth goes into air as vapour; returns as rain, hail or snow and finally goes back to the ocean s. |
| This water then flows back into the oceans, rivers, and lakes, completing the cycle. | supported | Thus, water from the ocean and surface of the earth goes into air as vapour; returns as rain, hail or snow and finally goes back to the ocean s. |
| This continuous process keeps the water supply on land. | supported | This circulation of water between ocean and land is a continuous process. This maintains the supply of water on land. |

**What the book answers with:** ✓ water goes into the air as vapour by evaporation (and transpiration) · ✓ the vapour cools high up and condenses into droplets that appear as clouds · ✓ the drops fall as rain, hail or snow · ✓ the whole circulation is called the water cycle

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - BACK TO THE OCEANS - pp. 141-142
… He wonders if this is also condensation of water vapour near the ground. What do you think? We now know that water brought back to the surface of the earth by rain, hail or snow, goes back to oceans. Thus, water from the ocean and surface of the earth goes into air as vapour; returns as rain, hail or snow and finally goes back to the ocean s. The circulation of water in this manner is known as the water cycle (Fig.14.9). This circulation of water between ocean and land is a continuous process. This maintains the supply of water on land. 14.5 WHAT IF IT RAINS HEAVILY?
```
</details>

---

### `L7-only-rice-and-chapati` — At home I mostly eat only rice and chapati every day because I do not like vegetables or fruit very much. Can you tell me what a balanced diet actually means, which nutrients my food is supposed to contain, and what can happen to my body if I keep leaving some of them out?

**Retrieved:** 2 · **read:** 1 passage(s), 634 chars · **gold pages:** p.53, p.55 · **cited:** p.14, p.53

**Gold passage reached the prompt:** 1/3 quotes

**Answer**

> A balanced diet means having a mix of different foods that provide all the nutrients your body needs. Your diet should include a variety of foods like fruits, vegetables, grains, proteins, and fats. If you leave out some nutrients, like vitamins and minerals, it can affect how your body grows and fights diseases. A balanced diet helps you work better, stay healthy, and grow strong. To build a strong and healthy body, you need all nutrients in the right proportion and in sufficient quantities in your daily diet.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A balanced diet means having a mix of different foods that provide all the nutrients your body needs. | supported | A diet containing adequate quantities of all nutrients is called a Balanced Diet. |
| Your diet should include a variety of foods like fruits, vegetables, grains, proteins, and fats. | supported | A diet containing adequate quantities of all nutrients is called a Balanced Diet. |
| If you leave out some nutrients, like vitamins and minerals, it can affect how your body grows and fights diseases. | supported | To build a strong and healthy body, you need all nutrients in the right proportion and in sufficient quantities in your daily diet. Significance of a balanced diet : l An increased |
| A balanced diet helps you work better, stay healthy, and grow strong. | supported | To build a strong and healthy body, you need all nutrients in the right proportion and in sufficient quantities in your daily diet. |
| To build a strong and healthy body, you need all nutrients in the right proportion and in sufficient quantities in your daily diet. | supported | To build a strong and healthy body, you need all nutrients in the right proportion and in sufficient quantities in your daily diet. |

**What the book answers with:** ✓ a balanced diet has all the nutrients in adequate quantity · ✗ it names the nutrients: carbohydrates, fats, proteins, vitamins, minerals · ✗ missing nutrients cause deficiency diseases or malnutrition

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Nutrition and Diet - p. 53
All that we consume during the day is together called our 'diet'. A diet containing adequate quantities of all nutrients is called a Balanced Diet. To build a strong and healthy body, you need all nutrients in the right proportion and in sufficient quantities in your daily diet. Significance of a balanced diet : l An increased capacity to work. l Good physical and mental health. l Increased capacity to fight / resist diseases. l Helps in proper growth of the body. Apart from having a balanced diet, we also need to exercise regularly to keep ourselves fit and healthy. …
```
</details>

---

### `L8-crowbar-three-parts` — My father lifted a heavy stone out of the ground in our field using a long iron rod that he rested on top of a brick near the stone. What is that kind of machine called, what are its three parts, and can you tell me what each one of those three parts actually does?

**Retrieved:** 2 · **read:** 1 passage(s), 592 chars · **gold pages:** p.86 · **cited:** p.86, p.88

**Gold passage reached the prompt:** 0/4 quotes

**Answer**

> A fulcrum is a machine part that acts as a fulcrum, or pivot, for a lever. The fulcrum is the point around which the lever rotates. In your father's case, the fulcrum is the long iron rod that he used to lift the heavy stone. The three parts of a fulcrum machine are the fulcrum, the effort arm, and the load arm. The effort arm is the part of the fulcrum machine that the person uses to apply the force. The load arm is the part of the fulcrum machine that the load is placed on. The fulcrum machine works by applying a force to the effort arm, which causes the load arm to move, lifting the load.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A fulcrum is a machine part that acts as a fulcrum, or pivot, for a lever. | supported | This combination of an axle and a wheel is a simple machine. |
| The fulcrum is the point around which the lever rotates. | supported | This rod is called an 'axle'. When the axle starts rotating with the help of electricity, the wheel fitted to it also starts rotating. |
| In your father's case, the fulcrum is the long iron rod that he used to lift the heavy stone. | supported | This combination of an axle and a wheel is a simple machine. |
| The three parts of a fulcrum machine are the fulcrum, the effort arm, and the load arm. | **unsupported** | When the pedal of a bicycle is rotated, the wheel starts rotating. How does this happen ? A wheel and axle A pulley |
| The effort arm is the part of the fulcrum machine that the person uses to apply the force. | **CONTRADICTED** | When the pedal of a bicycle is rotated, the wheel starts rotating. How does this happen ? A wheel and axle |
| The load arm is the part of the fulcrum machine that the load is placed on. | **unsupported** | When the pedal of a bicycle is rotated, the wheel starts rotating. How does this happen ? A wheel and axle |
| The fulcrum machine works by applying a force to the effort arm, which causes the load arm to move, lifting the load. | **unsupported** | When the pedal of a bicycle is rotated, the wheel starts rotating. |

**What the book answers with:** ✓ the machine is a lever · ✓ its three parts are effort, load and fulcrum · ✓ the fulcrum is the support it rests on, and the lever turns about it · ✗ the load is the weight lifted or the force the lever acts against · ✗ the effort is the force applied at the other end to lift the load

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Fulcrum Effort - p. 88
… 1. All of you must have enjoyed sitting on a giant wheel. What makes the giant wheel go round ? The giant wheel is fitted to a rod at its centre. This rod is called an 'axle'. When the axle starts rotating with the help of electricity, the wheel fitted to it also starts rotating. This combination of an axle and a wheel is a simple machine. We see innumerable examples of its use. 2. When the pedal of a bicycle is rotated, the wheel starts rotating. How does this happen ? A wheel and axle A pulley How does it help to use a pulley ?
```
</details>

---

### `L9-drum-up-the-plank` — Outside the shop near my house I saw two men rolling a very heavy drum up a slanting wooden plank into a truck, instead of just lifting it straight up into it. Why does using that plank make their work easier, and is it true that a screw and an axe both work on the same idea as the plank?

**Retrieved:** 2 · **read:** 1 passage(s), 601 chars · **gold pages:** p.85, p.86 · **cited:** p.84, p.85

**Gold passage reached the prompt:** 1/3 quotes

**Answer**

> Using the slanting wooden plank makes the work easier because it reduces the force needed to lift the heavy drum. It's like rolling a ball down a ramp instead of carrying it straight up. A screw and an axe both work on the same idea as the plank: they use inclined planes to make tasks easier. A screw is like a rolled-up ramp, and an axe is like a flat ramp. Both help to reduce the force needed to move things up or down a slope.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Using the slanting wooden plank makes the work easier because it reduces the force needed to lift the heavy drum. | **unsupported** | Therefore, less force is required to fit a screw than to hammer a nail. |
| It's like rolling a ball down a ramp instead of carrying it straight up. | supported | A winding road or ghat that goes up a mountain is also like an inclined plane wrapped around the mountain. It helps big vehicles to climb up and down the mountain easily. |
| A screw and an axe both work on the same idea as the plank: they use inclined planes to make tasks easier. | supported | A winding road or ghat that goes up a mountain is also like an inclined plane wrapped around the mountain. |
| A screw is like a rolled-up ramp, and an axe is like a flat ramp. | supported | A screw is like a rolled up inclined plane made of an iron strip. |
| Both help to reduce the force needed to move things up or down a slope. | supported | Therefore, less force is required to fit a screw than to hammer a nail. In other words, a screw is like a rolled up inclined plane made of an iron strip. A winding road or ghat tha |

**What the book answers with:** ✓ a slanting plank is an inclined plane · ✓ using it means bearing less of the weight, so it is easier · ✗ a screw is a rolled up inclined plane · ✗ an axe is a wedge, two inclined planes joined

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Simple Machines - pp. 85-86
… Therefore, less force is required to fit a screw than to hammer a nail. In other words, a screw is like a rolled up inclined plane made of an iron strip. A winding road or ghat that goes up a mountain is also like an inclined plane wrapped around the mountain. It helps big vehicles to climb up and down the mountain easily. Two routes, namely, a pathway and a road are available to climb the mountain shown in the picture. Compare the time and strength and your convenience required to reach the mountain top. 12.5 : Ghat A CB A B A wedge
```
</details>

---

### `L10-bicycle-wheel` — When I ride my bicycle to school the wheels keep going round and round in the same place on the axle, but at the same time the whole bicycle keeps moving forward along the straight road. Are those two different kinds of motion, and what is each one of them called?

**Retrieved:** 2 · **read:** 1 passage(s), 516 chars · **gold pages:** p.65, p.67 · **cited:** p.67, p.103

**Gold passage reached the prompt:** 1/2 quotes

**Answer**

> Circular motion is the type of motion where an object moves along a circular path. When a girl rides a bicycle, the wheels move in circular paths around the axle, while the bicycle itself moves forward along a straight path. These are two different types of motion: circular motion for the wheels and translational motion for the bicycle.
> 
> Speed is a measure of how fast an object is moving. In the example of a bus traveling from Solapur to Pune, the speed is calculated by taking the ratio of the distance covered to the time taken. This helps us understand how quickly the bus is moving.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Circular motion is the type of motion where an object moves along a circular path. | supported | The motion of an object along a circular path is called circular motion. |
| When a girl rides a bicycle, the wheels move in circular paths around the axle, while the bicycle itself moves forward along a straight path. | supported | The motion of an object along a circular path is called circular motion. |
| These are two different types of motion: circular motion for the wheels and translational motion for the bicycle. | supported | The motion of an object along a circular path is called circular motion. |
| Speed is a measure of how fast an object is moving. | **CONTRADICTED** | Speed is a measure of how fast an object is moving. |
| In the example of a bus traveling from Solapur to Pune, the speed is calculated by taking the ratio of the distance covered to the time taken. | supported | A bus covers the distance of about two hundred kilometres from Solapur to Pune in five hours. How much distance does the bus cover in one hour ? While solving this example, we take |
| This helps us understand how quickly the bus is moving. | supported | While solving this example, we take the ratio of the distance traversed and the time required to traverse that distance. |

**What the book answers with:** ✗ the bicycle along the road is linear (rectilinear) motion · ✓ the wheel going round is circular motion

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Motion and Types of Motion - pp. 67-68
The motion of an object along a circular path is called circular motion.

Which types of motion are seen when a girl rides a bicycle as shown here ? Use your brain power !

Speed

A bus covers the distance of about two hundred kilometres from Solapur to Pune in five hours. How much distance does the bus cover in one hour ? While solving this example, we take the ratio of the distance traversed and the time required to traverse that distance.
```
</details>

---

### `L11-off-syllabus-metro` — Yesterday my uncle was telling us all about the new metro railway line that is being built in our city, and he said that the ticket prices are decided by the state government and that the coaches for it come from a big factory near Chennai. Can you explain to me how the ticket price of a metro train is actually decided, and which company makes those coaches?

**Retrieved:** 0 · **read:** 0 passage(s), 0 chars · **gold pages:** — · **cited:** none

**Gold passage reached the prompt:** 0/0 quotes

**Answer**

> The metro ticket price is decided by the state government, as they set the regulations and rules for the metro system. The actual price of a ticket is determined by the fare structure, which includes factors like the distance traveled and the time of day. The coaches for the metro trains are made by a big factory near Chennai, which specializes in producing high-quality coaches for public transport systems.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| The metro ticket price is decided by the state government, as they set the regulations and rules for the metro system. | **unsupported** | — |
| The actual price of a ticket is determined by the fare structure, which includes factors like the distance traveled and the time of day. | **unsupported** | — |
| The coaches for the metro trains are made by a big factory near Chennai, which specializes in producing high-quality coaches for public transport systems. | **unsupported** | — |

<details><summary>The excerpt block this answer was graded against</summary>

```
(nothing retrieved)
```
</details>

---

### `L12-concrete-colony` — In my colony almost the whole ground is covered with concrete roads and cement, so where does all that rainwater even go from there, and what are the two techniques that a school building like mine could actually use to collect it?

*Asked after* “What is rainwater harvesting?” *in the same session — the pronoun only resolves because that turn happened.*

**Retrieved:** 2 · **read:** 1 passage(s), 632 chars · **gold pages:** p.141, p.144 · **cited:** p.144

**Gold passage reached the prompt:** 0/3 quotes

**Answer**

> Rainwater harvesting involves collecting rainwater in a way that's practical and sustainable. The basic idea is to "catch water where it falls," which means collecting rainwater where it naturally falls on rooftops, parks, and other open areas. This rainwater is then stored for later use, reducing the need to rely on distant water sources.
> 
> In your colony, the rainwater that falls on the concrete roads and buildings flows into the drains and eventually to rivers or lakes. This water is then transported long distances, requiring significant effort to bring it back to homes. To address this issue, schools can implement two techniques for rainwater harvesting:
> 
> 1. **Rainwater Harvesting Tanks**: These are containers that collect rainwater directly from roofs. The collected water can be used for various purposes such as watering plants, cleaning, or flushing toilets.
> 
> 2. **Green Roofs and Rain Gardens**: These techniques involve planting vegetation on rooftops and incorporating permeable materials in the ground. This allows rainwater to seep into the soil, reducing the volume of water that needs to be transported to drains. This method can be used in both schools and residential areas.
> 
> By implementing these techniques, you can ensure that rainwater is stored locally, reducing the need for long-distance water transport and making your school more sustainable and self-reliant.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Rainwater harvesting involves collecting rainwater in a way that's practical and sustainable. | supported | One way of increasing the availability of water is to collect rainwater and store it for later use. Collecting rainwater in this way is called rainwater harvesting. |
| The basic idea is to "catch water where it falls," which means collecting rainwater where it naturally falls on rooftops, parks, and other open areas. | supported | The basic idea behind rainwater harvesting is "Catch water where it falls". |
| This rainwater is then stored for later use, reducing the need to rely on distant water sources. | supported | Collecting rainwater in this way is called rainwater harvesting. The basic idea behind rainwater harvesting is "Catch water where it falls". What happens to the rainwater that fall |
| In your colony, the rainwater that falls on the concrete roads and buildings flows into the drains and eventually to rivers or lakes. | supported | What happens to the rainwater that falls in places that are mostly covered with concrete roads and buildings? It flows into the drains, isn't it? |
| This water is then transported long distances, requiring significant effort to bring it back to homes. | supported | From there water goes to rivers or lakes, which could be far away. A lot of effort will then be required to get this water back into our homes as the water did not seep into the gr |
| To address this issue, schools can implement two techniques for rainwater harvesting: 1. | **unsupported** | Collecting rainwater in this way is called rainwater harvesting. |
| **Rainwater Harvesting Tanks**: These are containers that collect rainwater directly from roofs. | **unsupported** | Collecting rainwater in this way is called rainwater harvesting. |
| The collected water can be used for various purposes such as watering plants, cleaning, or flushing toilets. | supported | Collecting rainwater in this way is called rainwater harvesting. |
| **Green Roofs and Rain Gardens**: These techniques involve planting vegetation on rooftops and incorporating permeable materials in the ground. | **unsupported** | The basic idea behind rainwater harvesting is "Catch water where it falls". |
| This allows rainwater to seep into the soil, reducing the volume of water that needs to be transported to drains. | **unsupported** | Collecting rainwater in this way is called rainwater harvesting. The basic idea behind rainwater harvesting is "Catch water where it falls". |
| This method can be used in both schools and residential areas. | supported | Collecting rainwater in this way is called rainwater harvesting. |
| By implementing these techniques, you can ensure that rainwater is stored locally, reducing the need for long-distance water transport and making your school more sustainable and self-reliant. | supported | Collecting rainwater in this way is called rainwater harvesting. The basic idea behind rainwater harvesting is "Catch water where it falls". |

**What the book answers with:** ✗ concrete reduces the seepage of rainwater into the ground · ✓ rooftop rainwater harvesting pipes the roof water to a storage tank · ✗ the other option lets water enter the ground from the roadside drains

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] NCERT Class 6 Science - RAINWATER HARVESTING - p. 144
One way of increasing the availability of water is to collect rainwater and store it for later use. Collecting rainwater in this way is called rainwater harvesting. The basic idea behind rainwater harvesting is "Catch water where it falls". What happens to the rainwater that falls in places that are mostly covered with concrete roads and buildings? It flows into the drains, isn't it? From there water goes to rivers or lakes, which could be far away. A lot of effort will then be required to get this water back into our homes as the water did not seep into the ground. …
```
</details>

