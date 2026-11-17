# thai-meeting-transcribe — ปลั๊กอิน Claude Code ถอดเสียงประชุมภาษาไทย

ส่งไฟล์เสียงหรือวิดีโอการประชุมให้ Claude Code แล้วจะได้สองไฟล์:

- `ชื่อไฟล์.txt` เป็นข้อความถอดเสียงทั้งหมด มีเวลากำกับทุกบรรทัด เช่น `[00:12:34] ...` เพื่อเอาไปใช้ต่อได้
- `ชื่อไฟล์.summary.md` เป็นสรุปการประชุม มีประเด็นที่หารือ มติ งานที่ต้องทำ และประเด็นค้าง

การถอดเสียงทำบนเครื่องของคุณเองด้วย [Typhoon Whisper Turbo](https://huggingface.co/typhoon-ai/typhoon-whisper-turbo)
(Whisper ที่ฝึกเพิ่มสำหรับภาษาไทย) ผ่าน faster-whisper **เสียงประชุมไม่ถูกส่งออกไปภายนอก** ไม่ต้องใช้ API key และไม่มีค่าใช้จ่าย
(ข้อความถอดเสียงจะถูกส่งให้ Claude อ่านเพื่อทำสรุปตามปกติของ Claude Code)

ใช้ได้ทั้ง macOS และ Windows

## ติดตั้ง

พิมพ์ใน Claude Code:

```
/plugin marketplace add Jakkaphan-Chalongdej/speech-to-text
/plugin install thai-meeting-transcribe@speech-to-text
```

แค่นี้ก็ใช้ได้แล้ว ครั้งแรกที่สั่งถอดเสียง ถ้าเครื่องยังไม่มี `uv` (ตัวจัดการ Python ที่ปลั๊กอินใช้)
Claude จะขออนุญาตแล้วติดตั้งให้เอง ไม่ต้องติดตั้ง Python หรือ ffmpeg เอง

### ถ้าอยากติดตั้ง `uv` เอง (หรือ Claude ติดตั้งให้ไม่สำเร็จ)

macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

ติดตั้งเสร็จแล้วให้ปิดและเปิด Claude Code ใหม่

## วิธีใช้

พิมพ์ใน Claude Code ได้เลย เช่น

```
ถอดเสียงไฟล์ ~/Downloads/ประชุมทีม.m4a แล้วสรุปการประชุมให้หน่อย
```

หรือเรียกคำสั่งตรงๆ:

```
/thai-meeting-transcribe:transcribe ~/Downloads/ประชุมทีม.mp4
```

รองรับไฟล์ทั่วไป เช่น mp3, m4a, wav, mp4, mov, webm

## ควรรู้

- **ครั้งแรกจะช้ากว่าปกติ** เพราะต้องโหลดโมเดลขนาดประมาณ 1.6 GB
- **ความเร็ว (ต่อเสียง 1 ชั่วโมง โดยประมาณ):** Mac ชิป M ประมาณ 30 นาที (ใช้ GPU ของ Mac ให้อัตโนมัติ)
  PC ที่ไม่มีการ์ดจอ NVIDIA ประมาณ 30–60 นาทีหรือนานกว่า
- **การ์ดจอ NVIDIA (Windows):** ปลั๊กอินจะลองใช้ GPU ให้อัตโนมัติ ถ้าใช้ไม่ได้ (เช่น ยังไม่ได้ติดตั้ง CUDA 12 / cuDNN 9) จะสลับไปใช้ CPU เอง ไม่ต้องตั้งค่าอะไร
- **คุณภาพขึ้นกับเสียงที่อัด** ช่วงที่คนพูดชัดใกล้ไมค์จะถอดได้แม่นมาก ช่วงที่หลายคนพูดพร้อมกันหรืออยู่ไกลไมค์จะผิดเยอะ
  ปลั๊กอินกรองข้อความวนซ้ำและตัวอักษรภาษาอื่นที่โมเดลแต่งขึ้นออกให้แล้ว
- **ถ้าถอดค้างกลางทาง** (ปิดเครื่อง หรือกดยกเลิก) สั่งใหม่ด้วยไฟล์เดิมได้เลย จะทำต่อจากจุดที่ค้างไว้
- ถ้ามีไฟล์ `.txt` ชื่อเดียวกันอยู่แล้วที่ไม่ได้สร้างจากปลั๊กอินนี้ ปลั๊กอินจะไม่เขียนทับ Claude จะถามคุณก่อน
- ไฟล์ `ชื่อไฟล์.transcribe.json` ใช้เก็บสถานะสำหรับทำต่อจากจุดค้าง ลบทิ้งได้เมื่อได้ผลที่ต้องการแล้ว
- ชื่อคนและศัพท์เฉพาะอาจถอดผิด ในสรุปมีเวลาอ้างอิงไว้ให้กลับไปฟังตรวจสอบได้

## สถานะการทดสอบ

- macOS (Apple M5): ทดสอบกับเสียงประชุมภาษาไทยจริง 36 นาที ทั้งการถอดเสียง การทำต่อจากจุดค้าง และการไม่เขียนทับไฟล์ที่มีอยู่

### ผลเทียบโมเดล (คลิปประชุมจริง 5 นาที บน Apple M5)

| โมเดล | เวลา | ความแม่นภาษาไทย |
|---|---|---|
| **Typhoon Whisper Turbo + หน้าต่าง 15 วิ (ค่าเริ่มต้น)** | **147 วิ** | ดีที่สุด เกือบตรงทุกคำในช่วงที่พูดชัด |
| Typhoon Whisper Turbo + หน้าต่าง 30 วิ | 183 วิ | คำถูก แต่ข้อความหายไปเกือบครึ่ง (เกินจำนวน token ต่อหน้าต่าง) |
| Thonburian Whisper medium | 421 วิ | ดี แต่ช้า และข้อความหายแบบเดียวกัน |
| Thonburian Whisper small | 220 วิ | พอใช้ มีวนซ้ำ |
| whisper large-v3-turbo (OpenAI) | 181 วิ | คำไทยผิดเยอะ มีภาษาอื่นปน |

CPU 10 threads ช้ากว่า 4 threads (268 vs 250 วิ) เพราะ efficiency core ถ่วง จึงใช้เฉพาะ performance core
- Windows: ยังไม่ได้ทดสอบบนเครื่องจริง (best effort) ถ้าเจอปัญหา แจ้งพร้อมข้อความ error ได้เลย

## สำหรับผู้พัฒนา

```
.claude-plugin/marketplace.json                    # ทำให้ repo นี้เป็น marketplace
plugins/thai-meeting-transcribe/
  .claude-plugin/plugin.json
  skills/transcribe/SKILL.md                       # ขั้นตอนที่ Claude ทำตาม
  skills/transcribe/scripts/transcribe.py          # สคริปต์ถอดเสียง (รันด้วย uv run)
  skills/transcribe/references/summary-template.md
tests/test_transcribe.py
```

รันเทสต์:

```bash
uv run --no-project --python 3.12 --with pytest --with faster-whisper --with "av<19" pytest tests -q
```

ทดสอบสคริปต์ตรงๆ:

```bash
uv run plugins/thai-meeting-transcribe/skills/transcribe/scripts/transcribe.py ไฟล์เสียง.m4a
```
