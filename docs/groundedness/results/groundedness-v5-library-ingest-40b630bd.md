# Groundedness run — v5-library-ingest

2026-09-22T05:19:33+00:00 · tutor `qwen2.5:1.5b` · http://127.0.0.1:8756 · budget backend default · judge gemma3:4b (local, via Ollama)

Gold set `/Users/mayur/Projects/AI Labs/AI-tutor-poc/docs/groundedness/evalset.json` over *General Science (Class 6)*. Each answer is graded against the excerpt block that turn actually read, not against the pages it cited.

## Headline

| | |
|---|---|
| Groundedness (claims) | **90%** (34/38 claims supported) |
| Groundedness (per turn) | 92% |
| Contradictions | **1** claims, in 1 of 12 turns |
| Unsupported | 3 claims |
| Key coverage | 71% |
| Context recall | 46% of gold passages reached the prompt |
| Fully grounded turns | 10/12 |
| Supported on a quote not in the excerpt | 0 — judge slips, check by hand |
| Off-syllabus abstention | held |

| outcome | turns |
|---|---|
| grounded and complete | 8 |
| grounded but thin | 2 |
| abstained | 1 |
| contradicts the book | 1 |
| right, but not from the book | 1 |

## The judge, graded first

11/14 known verdicts correct. It missed real support 0% of the time and waved a false claim through 12% of the time — the error bars on every number above.

| statement | expected | judge said |
|---|---|---|
| During sublimation the solid first melts into a liquid and then becomes a gas. | contradicted | unsupported |
| A lever is an example of a second-class machine with the load between the effort and the fulcrum. | unsupported | supported |
| Like poles of two magnets attract each other. | contradicted | unsupported |

## Per item

| item | grounded | key | recall | claims | outcome |
|---|---|---|---|---|---|
| `A1-shadow` | 100% | 100% | 67% | 2 | grounded and complete |
| `A2-friction` | 60% | 50% | 67% | 5 | right, but not from the book |
| `A3-gravity` | 100% | 0% | 0% | 3 | grounded but thin |
| `A4-sublimation` | 100% | 100% | 67% | 5 | grounded and complete |
| `A5-lever` | 50% | 100% | 0% | 4 | contradicts the book |
| `A6-sound` | 100% | 50% | 0% | 2 | grounded and complete |
| `A7-magnet-poles` | 100% | 100% | 100% | 5 | grounded and complete |
| `A8-balanced-diet` | 100% | 100% | 100% | 2 | grounded and complete |
| `A9-joints` | 100% | 50% | 25% | 5 | grounded and complete |
| `A10-inner-planets` | 100% | 100% | 100% | 2 | grounded and complete |
| `B1-reduce-friction` | 100% | 100% | 25% | 2 | grounded and complete |
| `B2-magnets-together` | 100% | 0% | 0% | 1 | grounded but thin |
| `C1-off-syllabus` | 0% | — | — | 3 | abstained |

---

### `A1-shadow` — What is a shadow?

**Retrieved:** 2 · **read:** 2 passage(s), 844 chars · **gold pages:** p.111 · **cited:** p.101

**Gold passage reached the prompt:** 2/3 quotes

**Answer**

> A shadow is the dark area formed when light cannot pass through an object. It appears on the opposite side of the object from the source of light.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A shadow is the dark area formed when light cannot pass through an object. | supported | The shadow of an object is formed only when light does not pass through the object. |
| It appears on the opposite side of the object from the source of light. | supported | The shadow of an object is formed only when light does not pass through the object. |

**What the book answers with:** ✓ a shadow is a dark part or dark area · ✓ it is caused by light being blocked by an object light cannot pass through

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Sound - p. 101
The shadow of an object is formed only when light does not pass through the object. The kind of shadow it forms depends upon the relative distances between the source of light, the object and the surface or the screen on which the shadow is formed. The shadow of an object formed due to sunlight is long in the mornings and evenings and short in the afternoon. We can easily note these changes if we observe the trees along the roadside. This change in the shadow depends on the source of light, the object and also on the surface on which the shadow is formed. …

[2] General Science (Class 6) - Sound - p. 101
As a result, the light does not reach a wall or any other surface on the other side of the object. That part remains dark. This dark part is called the 'shadow of the object'. Try this.
```
</details>

---

### `A2-friction` — What is frictional force?

**Retrieved:** 2 · **read:** 1 passage(s), 609 chars · **gold pages:** p.83 · **cited:** p.73, p.74

**Gold passage reached the prompt:** 2/3 quotes

**Answer**

> Frictional force is the force that resists the relative motion of surfaces sliding against each other. It's caused by the interaction between the molecules of two surfaces. When materials like rubber, plastic, or ebonite rub against each other, they create static electricity due to friction, resulting in an electrostatic force. This force is less for smooth surfaces and greater for rough surfaces. It's essential for our daily lives; without friction, we would slip and fall easily.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Frictional force is the force that resists the relative motion of surfaces sliding against each other. | **unsupported** | The smooth surfaces can be easily rubbed against each other because the force of friction between them is less, while rough surfaces cannot be easily rubbed against each other beca |
| It's caused by the interaction between the molecules of two surfaces. | **unsupported** | Static electricity is produced on materials like rubber, plastic and ebonite due to friction. |
| When materials like rubber, plastic, or ebonite rub against each other, they create static electricity due to friction, resulting in an electrostatic force. | supported | Static electricity is produced on materials like rubber, plastic and ebonite due to friction. |
| This force is less for smooth surfaces and greater for rough surfaces. | supported | The smooth surfaces can be easily rubbed against each other because the force of friction between them is less, while rough surfaces cannot be easily rubbed against each other beca |
| It's essential for our daily lives; without friction, we would slip and fall easily. | supported | It is possible for us to walk on the ground only because of the force of friction. If there is no friction, we would slip and fall. |

**What the book answers with:** ✓ friction arises when two surfaces rub against each other · ✗ it acts against the direction of motion

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Frictional force - p. 73
Static electricity is produced on materials like rubber, plastic and ebonite due to friction. The force exerted by such electrically charged materials is called electrostatic force . The smooth surfaces can be easily rubbed against each other because the force of friction between them is less, while rough surfaces cannot be easily rubbed against each other because the force of friction between them is much greater. It is possible for us to walk on the ground only because of the force of friction. If there is no friction, we would slip and fall. …
```
</details>

---

### `A3-gravity` — What is gravitational force?

**Retrieved:** 2 · **read:** 1 passage(s), 618 chars · **gold pages:** p.81 · **cited:** p.71, p.72

**Gold passage reached the prompt:** 0/3 quotes

**Answer**

> The gravitational force is the force that attracts two objects with mass towards each other. It is the force that keeps the planets in orbit around the sun and the moon in orbit around the Earth. The gravitational force is the weight of an object, which is the force that pulls an object towards the center of the Earth.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| The gravitational force is the force that attracts two objects with mass towards each other. | supported | The gravitational force operates between the sun and the planets in the solar system. |
| It is the force that keeps the planets in orbit around the sun and the moon in orbit around the Earth. | supported | The gravitational force operates between the sun and the planets in the solar system. |
| The gravitational force is the weight of an object, which is the force that pulls an object towards the center of the Earth. | supported | The gravitational force acting on an object is called the weight of that object. |

**What the book answers with:** ✗ the earth pulls objects towards itself · ✗ objects fall / come back down because of it

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Magnetic force - p. 72
… At the same time, the force of the tension in the spring constantly pulls the object upwards. The object comes to rest when the tension in the spring and the gravitational force on the object become equal. In this position, the scale on the spring balance shows the gravitational force acting on the object which is the weight of the object. The gravitational force acting on an object is called the weight of that object. The gravitational force operates between the sun and the planets in the solar system. Because of this, the planets revolve around the sun.
```
</details>

---

### `A4-sublimation` — What is sublimation?

**Retrieved:** 1 · **read:** 1 passage(s), 504 chars · **gold pages:** p.46 · **cited:** p.35

**Gold passage reached the prompt:** 2/3 quotes

**Answer**

> Sublimation is the process where a solid substance changes directly into a gas or vapor without going through the liquid phase. This occurs when the substance, like iodine, is heated. The iodine crystals do not melt; instead, they sublime, turning directly into a gas. When the iodine gas hits the walls of the funnel, it cools and forms solid crystals, sticking to the walls. This process is called sublimation.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Sublimation is the process where a solid substance changes directly into a gas or vapor without going through the liquid phase. | supported | The change of a solid substance directly into a gas or vapour without first changing into a liquid is called sublimation. |
| This occurs when the substance, like iodine, is heated. | supported | When the fumes of iodine hit the walls of the funnel they cool to form solid crystals of iodine and stick to the funnel walls. Thus, on heating, iodine does not melt and change to  |
| The iodine crystals do not melt; instead, they sublime, turning directly into a gas. | supported | Sublimation Iodine crystals do not melt on heating but change directly to the gaseous state. |
| When the iodine gas hits the walls of the funnel, it cools and forms solid crystals, sticking to the walls. | supported | Thus, on heating, iodine does not melt and change to a liquid but directly changes to the gaseous state. |
| This process is called sublimation. | supported | The change of a solid substance directly into a gas or vapour without first changing into a liquid is called sublimation. |

**What the book answers with:** ✓ a solid changes directly into a gas or vapour · ✓ without first becoming a liquid

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - War Drought - pp. 35-36
… Sublimation Iodine crystals do not melt on heating but change directly to the gaseous state. When the fumes of iodine hit the walls of the funnel they cool to form solid crystals of iodine and stick to the funnel walls. Thus, on heating, iodine does not melt and change to a liquid but directly changes to the gaseous state. The change of a solid substance directly into a gas or vapour without first changing into a liquid is called sublimation.
```
</details>

---

### `A5-lever` — What is a lever?

**Retrieved:** 2 · **read:** 1 passage(s), 606 chars · **gold pages:** p.96 · **cited:** p.86, p.90

**Gold passage reached the prompt:** 0/2 quotes

**Answer**

> A lever is a simple machine that uses a rigid bar to change the direction or magnitude of a force. It consists of a rigid bar pivoted at a fixed point called the fulcrum. The force is applied at a distance from the fulcrum, either to the left or right. The lever's efficiency depends on the distance of the force from the fulcrum and the distance between the fulcrum and the load it lifts.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A lever is a simple machine that uses a rigid bar to change the direction or magnitude of a force. | supported | Classify the following as a lever, a pulley and an inclined plane : A wedge, a needle, a staircase, a slide, the wheel of a flagpole, nutcrackers, scissors, an opener, an axe, a cr |
| It consists of a rigid bar pivoted at a fixed point called the fulcrum. | **CONTRADICTED** | the wheel of a flagpole |
| The force is applied at a distance from the fulcrum, either to the left or right. | supported | Ravi and Savita sit on a sea-saw in a garden. In the mean time, a gardener is trimming trees in the garden. He puts the leaves and other garbage in the wheelbarrow. |
| The lever's efficiency depends on the distance of the force from the fulcrum and the distance between the fulcrum and the load it lifts. | **unsupported** | Ravi and Savita sit on a sea-saw in a garden. In the mean time, a gardener is trimming trees in the garden. He puts the leaves and other garbage in the wheelbarrow. Later, Ravi get |

**What the book answers with:** ✓ a lever is a (simple) machine · ✓ its parts are effort, load and fulcrum

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Fulcrum Effort - p. 90
1. Classify the following as a lever, a pulley and an inclined plane : A wedge, a needle, a staircase, a slide, the wheel of a flagpole, nutcrackers, scissors, an opener, an axe, a crane, a knife. 6. Name the levers mentioned in the following passage. Identify the fulcrum, load and effort of each and say which type of lever it is. Ravi and Savita sit on a sea-saw in a garden. In the mean time, a gardener is trimming trees in the garden. He puts the leaves and other garbage in the wheelbarrow. Later, Ravi gets thirsty and he buys lemon sherbet. …
```
</details>

---

### `A6-sound` — How is sound produced?

**Retrieved:** 2 · **read:** 1 passage(s), 282 chars · **gold pages:** p.102 · **cited:** p.91, p.92

**Gold passage reached the prompt:** 0/1 quotes

**Answer**

> Sound is produced when an object vibrates, causing the air around it to vibrate as well. This vibration creates waves that travel through the air, eventually reaching our ears, where they are perceived as sound.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Sound is produced when an object vibrates, causing the air around it to vibrate as well. | supported | Some sounds are loud and are heard easily while some others are very soft and cannot be heard unless we listen attentively. |
| This vibration creates waves that travel through the air, eventually reaching our ears, where they are perceived as sound. | supported | Some sounds are loud and are heard easily while some others are very soft and cannot be heard unless we listen attentively. |

**What the book answers with:** ✓ sound is produced by vibration · ✗ when the vibration stops the sound stops

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Fulcrum Effort - p. 91
Some sounds are loud and are heard easily while some others are very soft and cannot be heard unless we listen attentively. We like some sounds. On the other hand, we get annoyed by some other sounds.

How are sounds produced ?
```
</details>

---

### `A7-magnet-poles` — What are the poles of a magnet?

**Retrieved:** 2 · **read:** 1 passage(s), 599 chars · **gold pages:** p.117 · **cited:** p.107

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> A magnet has two poles: a north pole and a south pole. The north pole points to the north, and the south pole points to the south. These poles are indicated by 'N' for the north pole and 'S' for the south pole. When an iron filings experiment is conducted, the filings stick most to the north pole and fewer to the south pole of the magnet. This experiment demonstrates that magnets always align themselves in the north-south direction.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A magnet has two poles: a north pole and a south pole. | supported | The end of a magnet that points to the north is called the north pole while the end that points to the south is called the south pole. |
| The north pole points to the north, and the south pole points to the south. | supported | The end of a magnet that points to the north is called the north pole while the end that points to the south is called the south pole. |
| These poles are indicated by 'N' for the north pole and 'S' for the south pole. | supported | The north pole is indicated by 'N' and the south pole, by 'S'. |
| When an iron filings experiment is conducted, the filings stick most to the north pole and fewer to the south pole of the magnet. | supported | The north pole is indicated by 'N' and the south pole, by 'S'. |
| This experiment demonstrates that magnets always align themselves in the north-south direction. | supported | A magnet always settles in the north-south direction. |

**What the book answers with:** ✓ the north pole is the end that points north · ✓ the south pole is the end that points south

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Fun with Magnets - p. 107
The end of a magnet that points to the north is called the north pole while the end that points to the south is called the south pole. The north pole is indicated by 'N' and the south pole, by 'S'.

2. Place some iron filings on a sheet of paper and pass a bar magnet over them. Pick up the bar magnet by holding it in the centre. What do you see ?

To which part of the magnet do most of the iron filings stick ? On which part do we see fewer filings ? What can we conclude from this ?

A magnet always settles in the north-south direction.
```
</details>

---

### `A8-balanced-diet` — What is a balanced diet?

**Retrieved:** 2 · **read:** 1 passage(s), 634 chars · **gold pages:** p.63 · **cited:** p.53, p.56

**Gold passage reached the prompt:** 3/3 quotes

**Answer**

> A balanced diet is a meal plan that includes all the essential nutrients in the right quantities and proportions to keep the body healthy and strong. It's important because it helps you work better, feel good mentally and physically, fight diseases, and grow big and strong.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A balanced diet is a meal plan that includes all the essential nutrients in the right quantities and proportions to keep the body healthy and strong. | supported | A diet containing adequate quantities of all nutrients is called a Balanced Diet. To build a strong and healthy body, you need all nutrients in the right proportion and in sufficie |
| It's important because it helps you work better, feel good mentally and physically, fight diseases, and grow big and strong. | supported | Significance of a balanced diet : l An increased capacity to work. l Good physical and mental health. l Increased capacity to fight / resist diseases. l Helps in proper growth of t |

**What the book answers with:** ✓ it contains all the nutrients in adequate quantity · ✓ why it matters -- work, health, resisting disease or growth

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Nutrition and Diet - p. 53
All that we consume during the day is together called our 'diet'. A diet containing adequate quantities of all nutrients is called a Balanced Diet. To build a strong and healthy body, you need all nutrients in the right proportion and in sufficient quantities in your daily diet. Significance of a balanced diet : l An increased capacity to work. l Good physical and mental health. l Increased capacity to fight / resist diseases. l Helps in proper growth of the body. Apart from having a balanced diet, we also need to exercise regularly to keep ourselves fit and healthy. …
```
</details>

---

### `A9-joints` — What are the types of joints in our body?

**Retrieved:** 2 · **read:** 1 passage(s), 519 chars · **gold pages:** p.71 · **cited:** p.60, p.61

**Gold passage reached the prompt:** 1/4 quotes

**Answer**

> Joints in our body are like special connections between bones that help us move. There are three main types: hinge joints, ball and socket joints, and gliding joints. Hinge joints allow bones to move in one direction, like the elbow or knee. Ball and socket joints let bones move in all directions, like the shoulder or hip. Gliding joints let bones slide over each other, like the wrist or ankle.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Joints in our body are like special connections between bones that help us move. | supported | This type of joint allows the movements of bones only in one direction. It moves in a 180 0 angle. |
| There are three main types: hinge joints, ball and socket joints, and gliding joints. | supported | This type of joint allows the movements of bones only in one direction. It moves in a 180 0 angle. Examples : the elbow and knee joints. 2. Ball and socket joint : In this type of  |
| Hinge joints allow bones to move in one direction, like the elbow or knee. | supported | This type of joint allows the movements of bones only in one direction. It moves in a 180 0 angle. Examples : the elbow and knee joints. |
| Ball and socket joints let bones move in all directions, like the shoulder or hip. | supported | In this type of joint, the bones can move in two or more directions - in a 360 0 angle. |
| Gliding joints let bones slide over each other, like the wrist or ankle. | supported | In this type of joint, the bones can only slide over each other. Examples : wrist and ankle joints. |

**What the book answers with:** ✓ a joint is where two or more bones are connected · ✗ there are two types -- movable and immovable

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Long bones - p. 61
Let us study some types of movable joints. 1. Hinge joint : This type of joint allows the movements of bones only in one direction. It moves in a 180 0 angle. Examples : the elbow and knee joints. 2. Ball and socket joint : In this type of joint, the bones can move in two or more directions - in a 360 0 angle. Examples : shoulder and hip joints. 3. Gliding joint : In this type of joint, the bones can only slide over each other. Examples : wrist and ankle joints. …
```
</details>

---

### `A10-inner-planets` — Which are the inner planets?

**Retrieved:** 2 · **read:** 1 passage(s), 469 chars · **gold pages:** p.124 · **cited:** p.114, p.115

**Gold passage reached the prompt:** 2/2 quotes

**Answer**

> The inner planets are Mercury, Venus, Earth, and Mars. These planets are closer to the sun and have a solid surface.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| The inner planets are Mercury, Venus, Earth, and Mars. | supported | The Mercury, Venus, Earth and Mars are the inner planets |
| These planets are closer to the sun and have a solid surface. | supported | The Mercury, Venus, Earth and Mars are the inner planets whereas the Jupiter, Saturn, Uranus and Neptune are outer planets. |

**What the book answers with:** ✓ the inner planets are Mercury, Venus, Earth and Mars

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - The Universe - p. 114
The solar system consists of the sun, the planets, asteroids, comets and meteors. The planets Mercury, Venus, Mars, Jupiter and Saturn can be easily seen.

The Mercury, Venus, Earth and Mars are the inner planets whereas the Jupiter, Saturn, Uranus and Neptune are outer planets.

Outer planets have rings around them. The crust of all the inner planets is hard. The outer planets have gaseous outer cover.

The sun
```
</details>

---

### `B1-reduce-friction` — How can we reduce it?

*Asked after* “What is frictional force?” *in the same session — the pronoun only resolves because that turn happened.*

**Retrieved:** 2 · **read:** 1 passage(s), 609 chars · **gold pages:** p.83, p.84, p.99 · **cited:** p.73, p.75

**Gold passage reached the prompt:** 1/4 quotes

**Answer**

> To reduce friction, you can apply a thin layer of lubricant, like oil or graphite, between surfaces that need to move against each other. This reduces the force of friction, allowing the surfaces to slide smoothly without slipping.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| To reduce friction, you can apply a thin layer of lubricant, like oil or graphite, between surfaces that need to move against each other. | supported | The smooth surfaces can be easily rubbed against each other because the force of friction between them is less, while rough surfaces cannot be easily rubbed against each other beca |
| This reduces the force of friction, allowing the surfaces to slide smoothly without slipping. | supported | The smooth surfaces can be easily rubbed against each other because the force of friction between them is less, while rough surfaces cannot be easily rubbed against each other beca |

**What the book answers with:** ✓ oil or a lubricant between rubbing parts · ✓ smoother surfaces have less friction

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Frictional force - p. 73
Static electricity is produced on materials like rubber, plastic and ebonite due to friction. The force exerted by such electrically charged materials is called electrostatic force . The smooth surfaces can be easily rubbed against each other because the force of friction between them is less, while rough surfaces cannot be easily rubbed against each other because the force of friction between them is much greater. It is possible for us to walk on the ground only because of the force of friction. If there is no friction, we would slip and fall. …
```
</details>

---

### `B2-magnets-together` — What happens when we bring two of them together?

*Asked after* “What are the poles of a magnet?” *in the same session — the pronoun only resolves because that turn happened.*

**Retrieved:** 2 · **read:** 1 passage(s), 640 chars · **gold pages:** p.118 · **cited:** p.107, p.108

**Gold passage reached the prompt:** 0/2 quotes

**Answer**

> When you bring two magnets together, they repel each other.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| When you bring two magnets together, they repel each other. | supported | The magnetic force is concentrated at the two ends or poles of a magnet. |

**What the book answers with:** ✗ like poles repel · ✗ opposite poles attract

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Fun with Magnets - p. 107
3. Take a bar magnet that can be cut with scissors or a knife. Take iron filings on a sheet of paper and place the magnet on it. Most of the iron filings will be seen to stick to its poles.

Now cut the magnet into two pieces as shown in the picture and place those pieces on iron filings. Pick up each of the pieces and observe them.

What do you find ?

The magnetic force is concentrated at the two ends or poles of a magnet.

If a magnet is divided into two parts, two independent magnets are formed.

It means that the two poles of a magnet cannot be separated from each other.
```
</details>

---

### `C1-off-syllabus` — Who won the 2022 football world cup?

**Retrieved:** 0 · **read:** 0 passage(s), 0 chars · **gold pages:** — · **cited:** none

**Gold passage reached the prompt:** 0/0 quotes

**Answer**

> The 2022 FIFA World Cup was won by the Argentina national football team. They defeated France 4-2 in the final match held in Qatar. This victory marked Argentina's first World Cup title in their history.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| The 2022 FIFA World Cup was won by the Argentina national football team. | **unsupported** | — |
| They defeated France 4-2 in the final match held in Qatar. | **unsupported** | — |
| This victory marked Argentina's first World Cup title in their history. | **unsupported** | — |

<details><summary>The excerpt block this answer was graded against</summary>

```
(nothing retrieved)
```
</details>

