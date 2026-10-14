"""Explainable, local filename/folder classification. Never decodes or moves audio."""
import re

# Order is deliberate: specific uses precede broad moods and instruments.
RULES = [
    ('logo', '片头 / Logo', '配乐', 'logo|ident|jingle|intro reveal|opening reveal|片头音乐|片尾音乐|片头小音乐|片尾小音乐|片头_片尾'),
    ('holiday', '节日庆典', '配乐', 'christmas|xmas|halloween|new year|圣诞|春节|新年|节日'),
    ('hiphop', '嘻哈 / 节拍', '配乐', 'hip hop|hiphop|trip hop|trap|boom bap|rap|rnb|r&b|嘻哈|说唱'),
    ('jazz', '爵士 / 放克', '配乐', 'jazz|funk|funky|soul|blues|爵士|放克|布鲁斯'),
    ('suspense', '悬疑 / 紧张', '配乐', 'suspense|horror|mystery|mysterious|conspiracy|thriller|tension|dark|恐怖|悬疑|紧张'),
    ('epic', '史诗 / 电影', '配乐', 'epic|epical|cinematic|trailer|orchestral|orchestra|dramatic|documentary|percussion|史诗|电影|管弦|震撼'),
    ('rock', '摇滚 / 动感', '配乐', 'rock|metal|sport|sports|action|stomp|energetic|energy|摇滚|动感|运动'),
    ('corporate', '企业 / 励志', '配乐', 'corporate|motivational|motivation|inspiring|inspiration|inspirational|uplifting|presentation|企业|励志|激励|宣传片'),
    ('happy', '轻快 / 活泼', '配乐', 'happy|upbeat|fun|funny|playful|comedy|ukulele|kids|children|轻快|欢快|活泼|快乐|滑稽|儿童'),
    ('electronic', '电子 / 舞曲', '配乐', 'electronic|edm|dance|house|techno|dubstep|synthwave|breakbeat|drum and bass|电子|舞曲'),
    ('ambient', '舒缓 / 氛围', '配乐', 'ambient|chill|chilling|chillout|lofi|lo fi|relax|relaxing|meditative|meditation|calm|peaceful|lounge|舒缓|治愈|冥想|安静|氛围'),
    ('emotional', '钢琴 / 抒情', '配乐', 'piano|emotional|romantic|sentimental|sad|beautiful|love|钢琴|抒情|浪漫|感人|悲伤'),
    ('acoustic', '民谣 / 原声', '配乐', 'acoustic|folk|country|guitar|民谣|吉他|乡村'),
    ('world', '民族 / 世界', '配乐', 'ethnic|world music|arabic|klezmer|民族|国风|古风'),
    ('pop', '流行音乐', '配乐', 'pop|流行'),
    ('transition', '转场 / 掠过', '音效', 'whoosh|whooshes|woosh|wooshes|swoosh|swooshes|swish|transition|reverse|riser|rise|sweep|roll by|flyby|fly by|转场|过渡|掠过|划过|呼啸|倒放'),
    ('impact', '冲击 / 爆炸', '音效', 'impact|hit|boom|explosion|explosive|slam|冲击|爆炸|重击|定音'),
    ('weapon', '武器 / 战斗', '音效', 'gun|gunshot|pistol|rifle|shotgun|revolver|machinegun|weapon|reload|bullet|sword|toy mech|toymech|武器|枪|子弹|刀剑'),
    ('tech', '科技 / 故障', '音效', 'glitch|sci fi|scifi|laser|robot|digital|cyber|space|spaceship|科技|故障|激光|宇宙|太空|电流|电子'),
    ('ui', '界面 / 提示', '音效', 'ui|interface|notification|button|click|keypress|8bit|8 bit|status|beep|alert|iphone|telephone|phone|message|操作音效|提示|点击|按键|得分|电话|手机|打字'),
    ('animal', '动物鸣叫', '音效', 'animal|bird|birds|dog|cat|horse|cow|whale|tiger|insect|wolf|lion|alligator|动物|鸟|狗|猫|马叫|牛叫|鲸鱼|老虎|昆虫|狼|狮子'),
    ('nature', '自然 / 环境', '音效', 'rain|wind|thunder|storm|ocean|sea|wave|water|river|stream|forest|fire|ice|weather|ambience|atmosphere|水|雨|风|雷|海浪|自然|环境|天气|森林|火焰'),
    ('voice', '人声 / 人群', '音效', 'voice|vocal|speech|crowd|human|male|female|laugh|scream|cough|sneeze|breath|applause|人声|人群|笑|尖叫|咳嗽|喷嚏|喷涕|呼吸|掌声|鼓掌|欢呼'),
    ('vehicle', '交通 / 载具', '音效', 'car|truck|motorcycle|bicycle|train|airplane|aircraft|helicopter|vehicle|traffic|engine|船|汽车|摩托|自行车|火车|飞机|直升机|交通|载具|引擎'),
    ('machine', '机械 / 工具', '音效', 'machine|machinery|tool|drill|saw|gear|motor|factory|mechanical|机械|工具|锉刀|钻|齿轮|工厂'),
    ('cartoon', '卡通 / 趣味', '音效', 'cartoon|boing|bubble|pop|卡通|泡泡|搞笑|网络音效|弹簧|Q弹|弹性|捏玩具'),
    ('sport', '体育 / 运动', '音效', 'sport|sports|bowling|basketball|football|tennis|体育|保龄球|羽毛球|篮球|足球|网球|高尔夫|溜冰|运动'),
    ('instrument', '乐器 / 铃声', '音效', 'instrument|bell|chime|drum|piano|guitar|乐器|佛教铃|铃声|风铃|鼓声|琴声'),
    ('foley', '生活 / 动作', '音效', 'foley|footstep|footsteps|door|cloth|plastic|wood|metal|paper|glass|step|slide|chair|chairs|sofa|coin|dices|rustle|switch|crumpling|人类动作|动作音效|细节音效|碰撞|脚步|开门|关门|衣服|布料|塑料|木|金属|纸|玻璃|摩擦|响指|生活|吃|喝|胶带|魔术贴|撕裂|易拉罐|拉锁|拉链|门|窗|家具|相机|快门|走路'),
]
CATEGORIES = [{'id': ident, 'name': name, 'group': group} for ident, name, group, _ in RULES]
CATEGORIES += [{'id':'music-other','name':'配乐待细分','group':'待分类'},
               {'id':'sfx-other','name':'音效待细分','group':'待分类'},
               {'id':'unknown','name':'信息不足','group':'待分类'}]
BY_ID = {c['id']: c for c in CATEGORIES}


def normalize(text):
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    return re.sub(r'[\W_]+', ' ', text.casefold()).strip()


def compile_terms(terms):
    # ASCII token boundaries keep "car" out of "scary", "hit" out of "white".
    return [(term, re.compile(re.escape(normalize(term)) if re.search(r'[^\x00-\x7f]', term)
                             else r'(?<![a-z0-9])'+re.escape(normalize(term))+r'(?![a-z])'))
            for term in terms.split('|')]


COMPILED = [(ident, group, compile_terms(terms)) for ident, _, group, terms in RULES]
SFX_CONTEXT = compile_terms('音效|sound effects|sound effect|sfx|foley')
MUSIC_CONTEXT = compile_terms('配乐|音乐|music|bgm|soundtrack')
SFX_SPECIFIC = compile_terms('paper crumpling|footsteps|gunshot|door slam|button click|magic chimes|sound effect|sound effects')


def matches(patterns, text):
    return next((term for term, pattern in patterns if pattern.search(text)), None)


def classify(item):
    # Only relative folders: a drive/root called 配乐 can also contain sound effects.
    path = item.get('relative_path') or item.get('original_name') or item.get('name', '')
    parts = re.split(r'[\\/]', path)
    filename = parts[-1].rsplit('.', 1)[0]
    components = [(filename, '名称')] + [(p, '文件夹') for p in reversed(parts[:-1])]
    normalized = [(original, origin, normalize(original)) for original, origin in components]
    domain = None
    for _, _, text in normalized[1:]:
        if matches(SFX_CONTEXT, text): domain = '音效'; break
        if matches(MUSIC_CONTEXT, text): domain = '配乐'; break
    if domain is None and any(matches(SFX_SPECIFIC, text) for _, _, text in normalized):
        domain = '音效'
    if domain is None and any('audiojungle' in text.replace(' ', '') for _, _, text in normalized):
        domain = '配乐'
    if domain is None:
        if matches(SFX_CONTEXT, normalized[0][2]): domain = '音效'
        elif matches(MUSIC_CONTEXT, normalized[0][2]): domain = '配乐'
    # The descriptive package folder often carries the genre while track.wav does not.
    for original, origin, text in normalized:
        for ident, group, patterns in COMPILED:
            if domain and group != domain: continue
            term = matches(patterns, text)
            if term:
                return {**BY_ID[ident], 'method':'auto', 'evidence':f'{origin}「{original}」含“{term}”'}
    ident = {'音效':'sfx-other', '配乐':'music-other'}.get(domain, 'unknown')
    return {**BY_ID[ident], 'method':'auto', 'evidence':'名称与文件夹信息不足，可试听后手动指定分类'}


def effective(automatic, override=None):
    if override in BY_ID:
        return {**BY_ID[override], 'method':'manual', 'evidence':'手动指定；重新扫描后仍保留',
                'automatic_id':automatic['id']}
    return {**automatic, 'automatic_id':automatic['id']}
