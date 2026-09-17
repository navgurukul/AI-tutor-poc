# Groundedness run — v3-reflow

2026-09-17T05:56:48+00:00 · tutor `qwen2.5:1.5b` · http://127.0.0.1:8757 · budget backend default · judge gemma3:4b (local, via Ollama)

Gold set `/Users/mayur/Projects/AI Labs/AI-tutor-poc/docs/groundedness/evalset.json` over *General Science (Class 6)*. Each answer is graded against the excerpt block that turn actually read, not against the pages it cited.

## Headline

| | |
|---|---|
| Groundedness (claims) | **90%** (26/29 claims supported) |
| Groundedness (per turn) | 87% |
| Contradictions | **0** claims, in 0 of 12 turns |
| Unsupported | 3 claims |
| Key coverage | 54% |
| Context recall | 32% of gold passages reached the prompt |
| Fully grounded turns | 8/12 |
| Supported on a quote not in the excerpt | 2 — judge slips, check by hand |
| Off-syllabus abstention | held |

| outcome | turns |
|---|---|
| grounded and complete | 6 |
| grounded but thin | 2 |
| right, but not from the book | 2 |
| ungrounded and incomplete | 2 |
| abstained | 1 |

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
| `A1-shadow` | 100% | 100% | 33% | 2 | grounded and complete |
| `A2-friction` | 100% | 50% | 67% | 4 | grounded and complete |
| `A3-gravity` | 100% | 0% | 0% | 2 | grounded but thin |
| `A4-sublimation` | 100% | 50% | 67% | 4 | grounded and complete |
| `A5-lever` | 100% | 100% | 0% | 3 | grounded and complete |
| `A6-sound` | 100% | 100% | 0% | 3 | grounded and complete |
| `A7-magnet-poles` | 67% | 50% | 100% | 3 | right, but not from the book |
| `A8-balanced-diet` | 100% | 100% | 67% | 3 | grounded and complete |
| `A9-joints` | 100% | 0% | 25% | 3 | grounded but thin |
| `A10-inner-planets` | 0% | 100% | 0% | 2 | right, but not from the book |
| `B1-reduce-friction` | — | 0% | 25% | 0 | ungrounded and incomplete |
| `B2-magnets-together` | — | 0% | 0% | 0 | ungrounded and incomplete |
| `C1-off-syllabus` | 0% | — | — | 4 | abstained |

---

### `A1-shadow` — What is a shadow?

**Retrieved:** 2 · **read:** 1 passage(s), 655 chars · **gold pages:** p.111 · **cited:** p.110, p.111

**Gold passage reached the prompt:** 1/3 quotes

**Answer**

> A shadow is the dark area that appears on the surface of an object when light is blocked by it. It's caused when light can't pass through the object, and the light that does reach the other side of the object falls on a surface, making that part of the surface dark.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A shadow is the dark area that appears on the surface of an object when light is blocked by it. | supported | This dark part is called the 'shadow of the object'. |
| It's caused when light can't pass through the object, and the light that does reach the other side of the object falls on a surface, making that part of the surface dark. | supported | This change in the shadow depends on the source of light, the object and also on the surface on which the shadow is formed. If an opaque object comes in the way of a light source,  |

**What the book answers with:** ✓ a shadow is a dark part or dark area · ✓ it is caused by light being blocked by an object light cannot pass through

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Voice box / Larynx - pp. 111-112
… This change in the shadow depends on the source of light, the object and also on the surface on which the shadow is formed. If an opaque object comes in the way of a light source, light does not pass through it. As a result, the light does not reach a wall or any other surface on the other side of the object. That part remains dark. This dark part is called the 'shadow of the object'. Try this. 1. Apparatus : A glass, water, a large white sheet of paper Place a glass filled with water on a sheet of paper in the window so that it receives direct sunlight. What is seen on the paper ?
```
</details>

---

### `A2-friction` — What is frictional force?

**Retrieved:** 2 · **read:** 2 passage(s), 741 chars · **gold pages:** p.83 · **cited:** p.83, p.84

**Gold passage reached the prompt:** 2/3 quotes

**Answer**

> Frictional force is the force that resists the relative motion of objects sliding against each other. It is caused by the interaction between the surfaces of two objects in contact, especially when they are moving. This force is responsible for the smooth sliding of materials like rubber, plastic, and ebonite, as well as the difficulty in moving rough surfaces. Without friction, objects would not be able to move at all, and we would slip and fall easily.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Frictional force is the force that resists the relative motion of objects sliding against each other. | supported | The smooth surfaces can be easily rubbed against each other because the force of friction between them is less, while rough surfaces cannot be easily rubbed against each other beca |
| It is caused by the interaction between the surfaces of two objects in contact, especially when they are moving. | supported | The smooth surfaces can be easily rubbed against each other because the force of friction between them is less, while rough surfaces cannot be easily rubbed against each other beca |
| This force is responsible for the smooth sliding of materials like rubber, plastic, and ebonite, as well as the difficulty in moving rough surfaces. | supported | The smooth surfaces can be easily rubbed against each other because the force of friction between them is less, while rough surfaces cannot be easily rubbed against each other beca |
| Without friction, objects would not be able to move at all, and we would slip and fall easily. | supported | It is possible for us to walk on the ground only because of the force of friction. If there is no friction, we would slip and fall. |

**What the book answers with:** ✓ friction arises when two surfaces rub against each other · ✗ it acts against the direction of motion

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Frictional force - p. 83
Static electricity is produced on materials like rubber, plastic and ebonite due to friction. The force exerted by such electrically charged materials is called electrostatic force . The smooth surfaces can be easily rubbed against each other because the force of friction between them is less, while rough surfaces cannot be easily rubbed against each other because the force of friction between them is much greater. It is possible for us to walk on the ground only because of the force of friction. If there is no friction, we would slip and fall. …

[2] General Science (Class 6) - Frictional force - p. 84
(muscular force, mechanical force, gravitational force, frictional force)
```
</details>

---

### `A3-gravity` — What is gravitational force?

**Retrieved:** 2 · **read:** 1 passage(s), 656 chars · **gold pages:** p.81 · **cited:** p.81, p.82

**Gold passage reached the prompt:** 0/3 quotes

**Answer**

> Gravitational force is the force that attracts two objects with mass towards each other. It is the force that keeps planets in orbit around the sun and that causes objects to fall when dropped.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Gravitational force is the force that attracts two objects with mass towards each other. | supported | The gravitational force operates between the sun and the planets in the solar system. |
| It is the force that keeps planets in orbit around the sun and that causes objects to fall when dropped. | supported | The gravitational force operates between the sun and the planets in the solar system. Because of this, the planets revolve around the sun. |

**What the book answers with:** ✗ the earth pulls objects towards itself · ✗ objects fall / come back down because of it

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Magnetic force - pp. 82-83
… In this position, the scale on the spring balance shows the gravitational force acting on the object which is the weight of the object. The gravitational force acting on an object is called the weight of that object. The gravitational force operates between the sun and the planets in the solar system. Because of this, the planets revolve around the sun. At the same time, gravity also operates between planets and their satellites. Then, why don't all the planets and satellites fall towards the sun ? Which forces are acting upon an aeroplane taking off into the sky ? Find out and discuss. …
```
</details>

---

### `A4-sublimation` — What is sublimation?

**Retrieved:** 1 · **read:** 1 passage(s), 650 chars · **gold pages:** p.46 · **cited:** p.45

**Gold passage reached the prompt:** 2/3 quotes

**Answer**

> Sublimation is the process where a solid substance directly changes into a gas or vapor without first becoming a liquid. This means the substance goes from a solid to a gas without going through the liquid phase. For example, when you heat iodine, it turns into a gas without becoming a liquid first. This happens because the molecules of iodine have enough energy to escape from the solid directly into the gas state.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Sublimation is the process where a solid substance directly changes into a gas or vapor without first becoming a liquid. | supported | Thus, on heating, iodine does not melt and change to a liquid but directly changes to the gaseous state. The change of a solid substance directly into a gas or vapour without first |
| This means the substance goes from a solid to a gas without going through the liquid phase. | supported | Thus, on heating, iodine does not melt and change to a liquid but directly changes to the gaseous state. The change of a solid substance directly into a gas or vapour without first |
| For example, when you heat iodine, it turns into a gas without becoming a liquid first. | supported | Thus, on heating, iodine does not melt and change to a liquid but directly changes to the gaseous state. |
| This happens because the molecules of iodine have enough energy to escape from the solid directly into the gas state. | supported | Thus, on heating, iodine does not melt and change to a liquid but directly changes to the gaseous state. The change of a solid substance directly into a gas or vapour without first |

**What the book answers with:** ✗ a solid changes directly into a gas or vapour · ✓ without first becoming a liquid

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Points Solids Liquids Gases - pp. 45-46
… Thus, on heating, iodine does not melt and change to a liquid but directly changes to the gaseous state. The change of a solid substance directly into a gas or vapour without first changing into a liquid is called sublimation. On opening a box of camphor, its smell spreads all around. Why does this happen ? Take some sand in a crucible. Put a few iodine crystals on it. Place the crucible on a tripod to heat it. Block the stem of the 5.7 : Identifying various substances and objects How will you identify the following? l A glass : Is it made of plastic, steel or glass ? …
```
</details>

---

### `A5-lever` — What is a lever?

**Retrieved:** 2 · **read:** 1 passage(s), 658 chars · **gold pages:** p.96 · **cited:** p.96

**Gold passage reached the prompt:** 0/2 quotes

**Answer**

> A lever is a simple machine that helps you lift heavy objects by using a force applied at a distance from the object being lifted. The force you apply is called the effort, and the distance from the fulcrum (pivot point) to the effort is called the effort arm. For example, a crowbar is a lever used to pry open a nail or a screwdriver is a lever used to remove a screw.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A lever is a simple machine that helps you lift heavy objects by using a force applied at a distance from the object being lifted. | supported | The force applied on the other end of the rod to lift the load is called the 'effort'. The part of the lever from the fulcrum to the effort is called the 'effort arm'. |
| The force you apply is called the effort, and the distance from the fulcrum (pivot point) to the effort is called the effort arm. | supported | The force applied on the other end of the rod to lift the load is called the 'effort'. The part of the lever from the fulcrum to the effort is called the 'effort arm'. |
| For example, a crowbar is a lever used to pry open a nail or a screwdriver is a lever used to remove a screw. | supported | Which tasks can be done using a lever ? Use your brain power ! |

**What the book answers with:** ✓ a lever is a (simple) machine · ✓ its parts are effort, load and fulcrum

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Simple Machines - pp. 96-97
… Archimedes' screw 3. The force applied on the other end of the rod to lift the load is called the 'effort'. The part of the lever from the fulcrum to the effort is called the 'effort arm'. Which tasks can be done using a lever ? Use your brain power ! edge of a knife becomes blunt, then the needle does not penetrate the cloth and the knife does not cut into the fruit. Why is this so ? less force is required to lift the paperweight. Such a lever is called a lever of the first order. 2. The picture shows how we use an opener to remove the cap of a sauce bottle. Try to do the same yourself. …
```
</details>

---

### `A6-sound` — How is sound produced?

**Retrieved:** 2 · **read:** 1 passage(s), 642 chars · **gold pages:** p.102 · **cited:** p.102

**Gold passage reached the prompt:** 0/1 quotes

**Answer**

> Sound is produced when objects vibrate, and the vibration causes the air around them to vibrate too, creating a wave that travels through the air. When the vibration stops, the sound stops. The source of sound is the object that vibrates.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Sound is produced when objects vibrate, and the vibration causes the air around them to vibrate too, creating a wave that travels through the air. | supported | When the vibration stops, the sound also stops. |
| When the vibration stops, the sound stops. | supported | When the vibration stops, the sound also stops. |
| The source of sound is the object that vibrates. | supported | When the vibration stops, the sound also stops. The object due to which sound is produced is called the source of that sound. |

**What the book answers with:** ✓ sound is produced by vibration · ✓ when the vibration stops the sound stops

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Voice box / Larynx - pp. 102-103
… When the vibration stops, the sound also stops. The object due to which sound is produced is called the source of that sound. Try this. Vocal cords 1. Take two balloons. Fill air in one and water in the other. Press the balloon filled with air against your ear as shown in the picture. Rub a finger on the balloon and listen to the sound. Repeat the same activity with the balloon filled with water. Through which balloon do we hear a clearer sound ? 2. Stand at the end of a big table and make a friend stand at the other end. Ask the friend to knock lightly on the table. …
```
</details>

---

### `A7-magnet-poles` — What are the poles of a magnet?

**Retrieved:** 2 · **read:** 1 passage(s), 645 chars · **gold pages:** p.117 · **cited:** p.117

**Gold passage reached the prompt:** 1/1 quotes

**Answer**

> Magnets have two ends, each with a unique property: one end points north (N) and the other south (S). These ends are called poles, and they attract each other. When a magnet is placed with its poles facing each other, they repel each other.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Magnets have two ends, each with a unique property: one end points north (N) and the other south (S). | supported | The end of a magnet that points to the north is called the north pole while the end that points to the south is called the south pole. The north pole is indicated by 'N' and the so |
| These ends are called poles, and they attract each other. | supported | The north pole is indicated by 'N' and the south pole, by 'S'. |
| When a magnet is placed with its poles facing each other, they repel each other. | **unsupported** | A magnet always settles in the north-south direction. |

**What the book answers with:** ✓ the north pole is the end that points north · ✗ the south pole is the end that points south

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Fun with Magnets - p. 117
… Do this many times. What do you observe ? The end of a magnet that points to the north is called the north pole while the end that points to the south is called the south pole. The north pole is indicated by 'N' and the south pole, by 'S'. 2. Place some iron filings on a sheet of paper and pass a bar magnet over them. Pick up the bar magnet by holding it in the centre. What do you see ? To which part of the magnet do most of the iron filings stick ? On which part do we see fewer filings ? What can we conclude from this ? A magnet always settles in the north-south direction. 3. …
```
</details>

---

### `A8-balanced-diet` — What is a balanced diet?

**Retrieved:** 2 · **read:** 1 passage(s), 651 chars · **gold pages:** p.63 · **cited:** p.63, p.66

**Gold passage reached the prompt:** 2/3 quotes

**Answer**

> A balanced diet is one that provides all the necessary nutrients in the right proportions and sufficient quantities to maintain good health. It includes a variety of foods like fruits, vegetables, dairy, and grains, as well as moderate amounts of fats and proteins. This ensures that the body gets the essential vitamins, minerals, and energy it needs to function properly and fight diseases.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| A balanced diet is one that provides all the necessary nutrients in the right proportions and sufficient quantities to maintain good health. | supported | To build a strong and healthy body, you need all nutrients in the right proportion and in sufficient quantities in your daily diet. |
| It includes a variety of foods like fruits, vegetables, dairy, and grains, as well as moderate amounts of fats and proteins. | supported | Fruits and vegetables Cereals and pulses Milk products, meat, fish, eggs |
| This ensures that the body gets the essential vitamins, minerals, and energy it needs to function properly and fight diseases. | supported | To build a strong and healthy body, you need all nutrients in the right proportion and in sufficient quantities in your daily diet. |

**What the book answers with:** ✓ it contains all the nutrients in adequate quantity · ✓ why it matters -- work, health, resisting disease or growth

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Nutrition and Diet - pp. 63-64
To build a strong and healthy body, you need all nutrients in the right proportion and in sufficient quantities in your daily diet. Significance of a balanced diet : l An increased capacity to work. l Good physical and mental health. l Increased capacity to fight / resist diseases. l Helps in proper growth of the body. Apart from having a balanced diet, we also need to exercise regularly to keep ourselves fit and healthy. Fatty substances (oil, ghee, butter) Scurvy Rickets Goitre Milk products, meat, fish, eggs Fruits and vegetables Cereals and pulses How to get a balanced diet ? …
```
</details>

---

### `A9-joints` — What are the types of joints in our body?

**Retrieved:** 2 · **read:** 1 passage(s), 623 chars · **gold pages:** p.71 · **cited:** p.71

**Gold passage reached the prompt:** 1/4 quotes

**Answer**

> Joints in our body are like hinges, ball-and-socket, or both. Hinge joints, like elbows and knees, allow movement in one direction. Ball-and-socket joints, like shoulders and hips, allow movement in multiple directions.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| Joints in our body are like hinges, ball-and-socket, or both. | supported | This type of joint allows the movements of bones only in one direction. It moves in a 180 0 angle. Examples : the elbow and knee joints. |
| Hinge joints, like elbows and knees, allow movement in one direction. | supported | This type of joint allows the movements of bones only in one direction. It moves in a 180 0 angle. Examples : the elbow and knee joints. |
| Ball-and-socket joints, like shoulders and hips, allow movement in multiple directions. | supported | In this type of joint, the bones can move in two or more directions - in a 360 0 angle. Examples : shoulder and hip joints. |

**What the book answers with:** ✗ a joint is where two or more bones are connected · ✗ there are two types -- movable and immovable

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Long bones - p. 71
… Move the different parts of your body from the head to the toes and observe the different places at which they can bend or turn. The bones in our body are connected to each other by means of ligaments. Types of joints Let us study some types of movable joints. 1. Hinge joint : This type of joint allows the movements of bones only in one direction. It moves in a 180 0 angle. Examples : the elbow and knee joints. 2. Ball and socket joint : In this type of joint, the bones can move in two or more directions - in a 360 0 angle. Examples : shoulder and hip joints. 3. …
```
</details>

---

### `A10-inner-planets` — Which are the inner planets?

**Retrieved:** 2 · **read:** 1 passage(s), 583 chars · **gold pages:** p.124 · **cited:** p.124, p.125

**Gold passage reached the prompt:** 0/2 quotes

**Answer**

> The inner planets are the planets located closest to the Sun. They are Mercury, Venus, Earth, and Mars.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| The inner planets are the planets located closest to the Sun. | **unsupported** | The crust of all the inner planets is hard. |
| They are Mercury, Venus, Earth, and Mars. | **unsupported** | — |

**What the book answers with:** ✓ the inner planets are Mercury, Venus, Earth and Mars

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - The Universe - p. 124
Outer planets have rings around them. The crust of all the inner planets is hard. The outer planets have gaseous outer cover. The sun The sun which is at the centre of the solar system is a yellow coloured star. Its surface temperature is around 6000°C. The size of the sun is so huge that around 13 lakh planets of the size of the earth can be easily placed within it. Due to the gravitational force of the sun, the celestial bodies in the solar system revolve around it. The diameter of the sun is approximately 13,92,000 km. …
```
</details>

---

### `B1-reduce-friction` — How can we reduce it?

*Asked after* “What is frictional force?” *in the same session — the pronoun only resolves because that turn happened.*

**Retrieved:** 2 · **read:** 2 passage(s), 741 chars · **gold pages:** p.83, p.84, p.99 · **cited:** p.83, p.84

**Gold passage reached the prompt:** 1/4 quotes

**Answer**

> (answered)

**What the book answers with:** ✗ oil or a lubricant between rubbing parts · ✗ smoother surfaces have less friction

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Frictional force - p. 83
Static electricity is produced on materials like rubber, plastic and ebonite due to friction. The force exerted by such electrically charged materials is called electrostatic force . The smooth surfaces can be easily rubbed against each other because the force of friction between them is less, while rough surfaces cannot be easily rubbed against each other because the force of friction between them is much greater. It is possible for us to walk on the ground only because of the force of friction. If there is no friction, we would slip and fall. …

[2] General Science (Class 6) - Frictional force - p. 84
(muscular force, mechanical force, gravitational force, frictional force)
```
</details>

---

### `B2-magnets-together` — What happens when we bring two of them together?

*Asked after* “What are the poles of a magnet?” *in the same session — the pronoun only resolves because that turn happened.*

**Retrieved:** 2 · **read:** 1 passage(s), 604 chars · **gold pages:** p.118 · **cited:** p.117

**Gold passage reached the prompt:** 0/2 quotes

**Answer**

> (answered)

**What the book answers with:** ✗ like poles repel · ✗ opposite poles attract

<details><summary>The excerpt block this answer was graded against</summary>

```
[1] General Science (Class 6) - Fun with Magnets - pp. 117-118
… If a magnet is divided into two parts, two independent magnets are formed. It means that the two poles of a magnet cannot be separated from each other. 4. Fix a powerful bar magnet to a stand as shown in the figure. Fix an iron bar at a short distance below the magnet. Take iron filings near the iron bar. What do you see ? After some time take the magnet away. What happens now ? Iron filings stick to the iron bar when the magnet is near it and fall off as soon as the magnet is taken away. That is, the magnetism in the bar vanishes. …
```
</details>

---

### `C1-off-syllabus` — Who won the 2022 football world cup?

**Retrieved:** 0 · **read:** 0 passage(s), 0 chars · **gold pages:** — · **cited:** none

**Gold passage reached the prompt:** 0/0 quotes

**Answer**

> The 2022 FIFA World Cup was won by the United States team. They defeated the France team in the final match held in Qatar. The United States team showcased their skills and teamwork, particularly in the second half of the match, to secure the victory. This win was a significant achievement for the United States, marking their first World Cup title in the sport's history.

| claim | verdict | the judge's line from the excerpt |
|---|---|---|
| The 2022 FIFA World Cup was won by the United States team. | **unsupported** | — |
| They defeated the France team in the final match held in Qatar. | **unsupported** | — |
| The United States team showcased their skills and teamwork, particularly in the second half of the match, to secure the victory. | **unsupported** | — |
| This win was a significant achievement for the United States, marking their first World Cup title in the sport's history. | **unsupported** | — |

<details><summary>The excerpt block this answer was graded against</summary>

```
(nothing retrieved)
```
</details>

