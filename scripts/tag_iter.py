tag = input("Enter tag:")
print("Generated url: https://gelbooru.com/index.php?page=post&s=list&tags=%s&pid=19992" % (tag,))
number = int(input("Enter id of the last picture on page: "))

number = ((number // 20000) + 1) * 20000

while number > 0 :
    print("%s id:>%i id:<%i" % (tag, number - 20000, number))
    number -= 20000