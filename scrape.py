from icrawler.builtin import BingImageCrawler
import os

def scrape_cars():
    # 1. Define your classes (Notice I tweaked the queries slightly for Bing)
    car_classes = {
        "police_car": "Singapore Police Force fast response car side profile",
        "hyundai_civic": "Hyundai Civic car side view profile", 
        "toyota_vios": "Toyota Vios car side view profile",
        "honda_vezel": "Honda Vezel car side view profile",
        "mazda_3": "Mazda 3 sedan car side profile",
        "mazda_6": "Mazda 6 sedan car side profile"
    }

    # 2. Set how many images you want per class
    max_images_per_class = 100
    
    # 3. Create the base dataset directory
    base_dir = r'C:\GitHub\INF2009-Project\custom_dataset'
    os.makedirs(base_dir, exist_ok=True)

    # 4. Loop through each class and start scraping
    for class_name, search_query in car_classes.items():
        print(f"\n---> Starting download for: {class_name}")
        
        class_dir = os.path.join(base_dir, class_name)
        os.makedirs(class_dir, exist_ok=True)

        # Switched to BingImageCrawler!
        crawler = BingImageCrawler(
            feeder_threads=1,
            parser_threads=2,
            downloader_threads=4,
            storage={'root_dir': class_dir}
        )

        # Run the search
        crawler.crawl(
            keyword=search_query, 
            filters={'type': 'photo'}, 
            max_num=max_images_per_class,
            file_idx_offset=0
        )
        
    print("\n✅ Scraping complete! Check your custom_dataset folder.")

if __name__ == '__main__':
    scrape_cars()