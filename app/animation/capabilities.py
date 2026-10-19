"""The AI receives the actual renderer contract, not a list of promised effects."""
from app.animation.schema import Animation,DATA
from app.animation.examples import examples


def capabilities():
    return {
        'version':'naman.animation.v1','canvas':{'width':1920,'height':1080,'fps':30},
        'limits':{'duration_seconds':30,'objects':32,'object_keyframes':64,'camera_keyframes':32,'total_particles':256},
        'record_contract':{'optional':True,'fields':['scene_id','sentence_indices','start','end','object_id','track','data','background_media','source_start'],
            'tracks':['layers','infographics','maps','emphasis'],
            'timing':'start/end ana proje saniyeleri; nesne ve kamera keyframe zamanı animasyonun başlangıcından itibaren saniyedir. sentence_indices sıfır tabanlı altyazı cümleleridir.',
            'background':'data.background=null mevcut medyanın üstünde şeffaf katmandır. background_media yalnız gerçek arşiv kimliğiyle bağımsız kaynak önerir; ayrı seçim/onay gerektirir.',
            'data_schema':Animation.model_json_schema()},
        'components':list(DATA),
        'component_data_schemas':{kind:model.model_json_schema() for kind,model in DATA.items()},
        'reference_basis':{'reviewed':300,'full_prompts':263,'partial_prompts':37,'note':'Referanslardan teknik parçalar çıkarıldı; 300 ayrı hazır efekt veya kaynak videoların yeniden yapımı değildir.'},
        'techniques':{'scientific':'Şematik bulut lobları, yönlü akış/oklar, tohumlu yıldırım, dalga ve sınırlı parçacıklar. Fizik/meteoroloji simülasyonu değildir.',
            'geography':'Mevcut harita_sahneleri/map ve infografikler/route/zoom şablonları korunur. Yeni bileşen içinde doğrulanmamış koordinat/harita çizilmez.',
            'infographics':'Sıfır tabanlı hareketli çubuk/çizgi grafik, sayaç. Sayılar ve etiketler anlatımdan doğrulanır veya zorunlu demo etiketi taşır.',
            'explanation':'Düğüm, bağlantı, yol çizimi, yön oku, 2D kesit kutuları, isometric_box (2.5D şema).',
            'cinematic':'Saniye bazlı X/Y, ölçek, dönüş, saydamlık keyframe; kamera X/Y/ölçek, katmanlara farklı hareketle 2.5D paralaks.',
            'typography':'Kısa, anlatımdaki metin; konum/ölçek/saydamlık ile giriş ve vurgu. Yazılar okunur kalır, glyph morph yok.'},
        'rules':['arrow, flow ve line nesneleri data.points ister: en az iki {"x":sayı,"y":sayı} noktası, nesnenin x,y konumuna göre ofset. Örnek: "data":{"points":[{"x":-300,"y":0},{"x":300,"y":0}],"speed":160}. points olmadan nesne reddedilir.',
                 'Serbest JS/Python/SVG/HTML, URL, dosya yolu, fizik betiği ve sınırsız döngü kabul edilmez.',
                 'Yeni veri veya olay uydurmayın. narration temeli sayıları ve metinleri gerçek sahne anlatımıyla doğrular; schematic ölçülü veri için kullanılamaz.',
                 'Demo ve şematik açıklaması zorunludur; kamera tarafından taşınmaz. Gerçek bilimsel simülasyon veya tam 3D/PBR iddiası yok.',
                 'Kullanıcı çizim yapmaz: bu nesneleri dış AI JSON ile birleştirir; NAMAN gerçek kareleri hesaplar. Her öneri önce taslak, sonra açık seçim/onaydır.'],
        'examples':examples(),
        'example_note':'Bu üç veri örneği DEMO’dur. Bunları kendi scene_id/cümle/saatlerine uyarlayın; gereksiz animasyon eklemeyin. Gerçek proje verileri için narration/schematic temelini kullanın.'}
